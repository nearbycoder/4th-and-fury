#include "FurySim.h"

// Match flow: setting up plays, choosing them, downs, scoring, quarters. The live action is in
// FurySimPlay.cpp and the computer players' decisions are in FurySimAI.cpp.

namespace
{
	using namespace Fury;

	constexpr float SelectSeconds = 14.f;
	constexpr float LineupSeconds = 1.5f;
	constexpr float FirstDownYards = 30.f;

	const TCHAR* Ordinal(int32 N)
	{
		switch (N) { case 1: return TEXT("1ST"); case 2: return TEXT("2ND"); case 3: return TEXT("3RD"); default: return TEXT("4TH"); }
	}
}

// ---------------------------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------------------------

void FFurySim::Emit(EFuryEvent Type, int32 Team, int32 Player, int32 Other, float Value)
{
	FFuryEvent Event;
	Event.Type = Type;
	Event.Team = Team;
	Event.Player = Player;
	Event.Other = Other;
	Event.Value = Value;
	Event.Pos = Player != INDEX_NONE ? FVector(Players[Player].P.X, Players[Player].P.Y, 0.f) : Ball.Pos;
	if (Other != INDEX_NONE && Player != INDEX_NONE &&
		(Type == EFuryEvent::Tackle || Type == EFuryEvent::BigHit || Type == EFuryEvent::Shove || Type == EFuryEvent::LateHit))
	{
		const FFurySimPlayer& V = Players[Other];
		const FVector2D Pad = V.P + (Players[Player].P - V.P).GetSafeNormal() * 15.f;
		Event.Pos = FVector(Pad, Players[Player].Act == EFuryAct::Dive || Players[Player].Act == EFuryAct::Tackle ? 85.f : 120.f);
		if (Type == EFuryEvent::LateHit) { WhistleFocus = Pad; }
	}
	Events.Add(Event);
}

FVector2D FFurySim::ToWorld(const FVector2D& PlaySpaceYards) const
{
	const float D = OffenseDir();
	return FVector2D(LosX + D * PlaySpaceYards.X * Yard, BallY + D * PlaySpaceYards.Y * Yard);
}

FVector2D FFurySim::ClampToField(const FVector2D& Point, float Margin) const
{
	return FVector2D(FMath::Clamp(Point.X, -EndLineX + Margin, EndLineX - Margin), FMath::Clamp(Point.Y, -SidelineY + Margin, SidelineY - Margin));
}

float FFurySim::YardsToGo() const
{
	return FMath::Max(0.f, (FirstDownX - LosX) * OffenseDir() / Yard);
}

bool FFurySim::GoalToGo() const
{
	return FirstDownX * OffenseDir() >= GoalX - 1.f;
}

FString FFurySim::DownText() const
{
	switch (PlayType)
	{
	case EFuryPlayType::Kickoff: return bKickPossessed && BallTeam != KickingTeam ? TEXT("KICK RETURN") : TEXT("KICKOFF");
	case EFuryPlayType::Punt: if (bKickPossessed && BallTeam != Offense) { return TEXT("PUNT RETURN"); } break;
	case EFuryPlayType::ExtraPoint: return TEXT("EXTRA POINT");
	case EFuryPlayType::TwoPoint: return TEXT("2-POINT TRY");
	default: break;
	}
	if (GoalToGo())
	{
		return FString::Printf(TEXT("%s & GOAL"), Ordinal(Down));
	}
	const int32 ToGo = FMath::Max(1, FMath::CeilToInt32(YardsToGo() - 0.05f));
	return FString::Printf(TEXT("%s & %d"), Ordinal(Down), ToGo);
}

FString FFurySim::SpotText() const
{
	const int32 Line = FMath::RoundToInt32(YardLine(Offense, LosX));
	if (Line == 50)
	{
		return TEXT("50");
	}
	return Line < 50 ? FString::Printf(TEXT("OWN %d"), FMath::Max(Line, 1)) : FString::Printf(TEXT("OPP %d"), FMath::Max(100 - Line, 1));
}

FString FFurySim::ClockText() const
{
	const int32 Total = FMath::Max(0, FMath::CeilToInt32(Clock - 0.001f));
	return FString::Printf(TEXT("%d:%02d"), Total / 60, Total % 60);
}

int32 FFurySim::Winner() const
{
	return Teams[0].Score == Teams[1].Score ? INDEX_NONE : (Teams[0].Score > Teams[1].Score ? 0 : 1);
}

int32 FFurySim::Captain(int32 Team) const
{
	// The play-caller rotates among a team's humans every drive, so everyone gets a turn.
	int32 Seated[MaxSeats];
	int32 Count = 0;
	for (int32 i = 0; i < MaxSeats; ++i)
	{
		if (Seats[i].bActive && Seats[i].Team == Team)
		{
			Seated[Count++] = i;
		}
	}
	return Count == 0 ? INDEX_NONE : Seated[TeamDrives[Team] % Count];
}

bool FFurySim::IsPassIconLive() const
{
	if (Phase != EFuryPhase::Live && Phase != EFuryPhase::PreSnap)
	{
		return false;
	}
	if (PlayType != EFuryPlayType::Scrimmage && PlayType != EFuryPlayType::TwoPoint)
	{
		return false;
	}
	return !bPassThrown && !bBallCrossedLine && !bChangeOfPossession;
}

bool FFurySim::IsPasser(int32 Index) const
{
	const FFurySimPlayer& P = Players[Index];
	const bool bScrimmage = PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint;
	return P.bHasBall && bScrimmage && P.Team == Offense && P.Slot == 0 && !bPassThrown && !bChangeOfPossession
		&& CurrentOff.Kind != EFuryPlayKind::Run && (P.P.X - LosX) * OffenseDir() < 0.f && (Phase == EFuryPhase::Live || Phase == EFuryPhase::PreSnap);
}

const FFuryOffPlay* FFurySim::OffenseChoice(int32 Page, int32 Cell) const
{
	const TArray<FFuryOffPlay>& All = FuryPlaybook::Offense();
	if (Page < 2)
	{
		const int32 Index = Page * FuryPlaybook::PlaysPerPage + Cell;
		return All.IsValidIndex(Index) ? &All[Index] : nullptr;
	}
	// The kicking page. Kicks make no sense on a two-point try.
	if (PlayType == EFuryPlayType::TwoPoint)
	{
		return nullptr;
	}
	return Cell == 0 ? &FuryPlaybook::Punt() : Cell == 1 ? &FuryPlaybook::FieldGoal() : nullptr;
}

const FFuryDefPlay* FFurySim::DefenseChoice(int32 Cell) const
{
	const TArray<FFuryDefPlay>& All = FuryPlaybook::Defense();
	return All.IsValidIndex(Cell) ? &All[Cell] : nullptr;
}

void FFurySim::AddFury(int32 Team, float Amount)
{
	FFuryTeamState& State = Teams[Team];
	if (State.InFury() || Phase == EFuryPhase::GameOver)
	{
		return;
	}
	State.Fury = FMath::Clamp(State.Fury + Amount, 0.f, 1.f);
	if (State.Fury >= 1.f)
	{
		State.FuryPlays = 3;
		Emit(EFuryEvent::FuryStart, Team);
	}
}

void FFurySim::TickFuryAfterPlay()
{
	for (int32 Team = 0; Team < 2; ++Team)
	{
		FFuryTeamState& State = Teams[Team];
		if (FuryAtSnap[Team] && State.FuryPlays > 0)
		{
			--State.FuryPlays;
			State.Fury = State.FuryPlays / 3.f;
			if (State.FuryPlays == 0)
			{
				Emit(EFuryEvent::FuryEnd, Team);
			}
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Match setup
// ---------------------------------------------------------------------------------------------

void FFurySim::SetSeat(int32 Index, bool bActive, int32 Team)
{
	Seats[Index] = FFurySeat();
	Seats[Index].bActive = bActive;
	Seats[Index].Team = Team;
}

void FFurySim::StartMatch(int32 HomeLeague, int32 AwayLeague, float QuarterSeconds, float InCpuSkill, int32 Seed)
{
	Random.Initialize(Seed);
	for (int32 Team = 0; Team < 2; ++Team)
	{
		Teams[Team] = FFuryTeamState();
		Teams[Team].League = Team == 0 ? HomeLeague : AwayLeague;
		Teams[Team].bHuman = false;
	}
	for (const FFurySeat& Seat : Seats)
	{
		if (Seat.bActive)
		{
			Teams[Seat.Team].bHuman = true;
		}
	}
	QuarterLength = QuarterSeconds;
	Clock = QuarterSeconds;
	Quarter = 1;
	CpuSkill = InCpuSkill;
	bOvertime = false;
	bTwoMinuteCalled = false;
	PlayCount = 0;
	DriveCount = 0;
	TeamDrives[0] = TeamDrives[1] = 0;
	bClockExpired = false;
	PendingScoreTeam = INDEX_NONE;
	ScoringTeam = Scorer = INDEX_NONE;
	Events.Reset();
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		Players[i] = FFurySimPlayer();
		Players[i].Team = i / TeamSize;
		Players[i].Slot = i % TeamSize;
		// Start everyone on their own sideline so the first lineup has somewhere to come from.
		Players[i].P = FVector2D((Players[i].Team == 0 ? -1.f : 1.f) * (600.f + 150.f * Players[i].Slot), -SidelineY + 200.f);
	}
	FMemory::Memzero(Trail);
	OpeningKicker = Random.RandRange(0, 1);
	BeginKickoff(OpeningKicker, 35.f);
}

void FFurySim::DebugFieldGoal(int32 NewOffense, float YardsFromOwnGoal)
{
	Offense = NewOffense;
	BallTeam = NewOffense;
	PlayType = EFuryPlayType::FieldGoal;
	LosX = WorldX(NewOffense, YardsFromOwnGoal);
	BallY = 0.f;
	Down = 4;
	FirstDownX = OffenseDir() * GoalX;
	CurrentOff = FuryPlaybook::FieldGoal();
	CurrentDef = FuryPlaybook::KickBlock();
	bHaveOffPlay = bHaveDefPlay = true;
	SetupPlay();
	Enter(EFuryPhase::Lineup);
}

void FFurySim::Enter(EFuryPhase NewPhase)
{
	Phase = NewPhase;
	PhaseTime = 0.f;
}

// ---------------------------------------------------------------------------------------------
// Units and line-ups
// ---------------------------------------------------------------------------------------------

/** Puts the right seven athletes on the field for each team and gives them their base ratings. */
void FFurySim::PlaceUnits(bool bOffenseUnit[2])
{
	for (int32 Team = 0; Team < 2; ++Team)
	{
		const FFuryTeam& Info = TeamInfo(Team);
		for (int32 Slot = 0; Slot < TeamSize; ++Slot)
		{
			FFurySimPlayer& P = Players[Global(Team, Slot)];
			P.Roster = bOffenseUnit[Team] ? OffenseSlot0 + Slot : DefenseSlot0 + Slot;
			const bool bKickPlay = PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint || PlayType == EFuryPlayType::Punt;
			if (bOffenseUnit[Team] && bKickPlay && Slot == 0)
			{
				P.Roster = KickerSlot;
			}
			if (PlayType == EFuryPlayType::Kickoff)
			{
				if (Team == KickingTeam)
				{
					P.Roster = Slot == 0 ? KickerSlot : DefenseSlot0 + Slot;
				}
				else
				{
					// Return unit: a linebacker and the linemen up front, receivers in the middle, the back deep.
					static const int32 ReturnRoster[TeamSize] = { DefenseSlot0 + 3, 1, 2, 3, 4, 5, 6 };
					P.Roster = ReturnRoster[Slot];
				}
			}
			P.Pos = Info.Roster[P.Roster].Pos;

			// Ratings 1..5 nudge the base numbers a few percent either way.
			const float SpeedBias = (Info.Speed - 3) * 0.022f;
			const float PowerBias = (Info.Power - 3) * 0.08f;
			float Base = 760.f;
			P.Radius = 42.f;
			P.Power = 0.5f + PowerBias;
			P.Hands = 0.9f;
			switch (P.Pos)
			{
			case EFuryPos::QB: Base = 735.f; P.Power = 0.38f + PowerBias; break;
			case EFuryPos::OL: Base = 610.f; P.Power = 0.82f + PowerBias; P.Radius = 52.f; P.Hands = 0.6f; break;
			case EFuryPos::DL: Base = 650.f; P.Power = 0.8f + PowerBias; P.Radius = 52.f; P.Hands = 0.6f; break;
			case EFuryPos::WR: Base = 800.f; P.Power = 0.4f + PowerBias; P.Hands = 0.93f + (Info.Passing - 3) * 0.012f; break;
			case EFuryPos::RB: Base = 790.f; P.Power = 0.62f + PowerBias; P.Hands = 0.88f; break;
			case EFuryPos::LB: Base = 755.f; P.Power = 0.68f + PowerBias; P.Hands = 0.72f; break;
			case EFuryPos::CB: Base = 795.f; P.Power = 0.42f + PowerBias; P.Hands = 0.78f + (Info.Defense - 3) * 0.02f; break;
			case EFuryPos::S: Base = 785.f; P.Power = 0.55f + PowerBias; P.Hands = 0.8f + (Info.Defense - 3) * 0.02f; break;
			case EFuryPos::K: Base = 700.f; P.Power = 0.3f; P.Hands = 0.7f; break;
			}
			P.TopSpeed = Base * (1.f + SpeedBias);
		}
	}
}

void FFurySim::AssignSeats()
{
	for (FFurySimPlayer& P : Players)
	{
		P.Seat = INDEX_NONE;
	}
	for (int32 Team = 0; Team < 2; ++Team)
	{
		// Which athletes the team's humans take, in order of importance.
		const int32* Roles;
		static const int32 OffenseRoles[4] = { 0, 4, 5, 6 };
		static const int32 DefenseRoles[4] = { 3, 6, 4, 5 };
		static const int32 KickRoles[4] = { 0, 3, 4, 2 };
		static const int32 ReturnRoles[4] = { 6, 4, 5, 0 };
		static const int32 PuntReturnRoles[4] = { 6, 3, 4, 5 };
		static const int32 BlockRoles[4] = { 3, 0, 2, 1 };
		const bool bHasBall = Team == Offense;
		switch (PlayType)
		{
		case EFuryPlayType::Kickoff: Roles = Team == KickingTeam ? KickRoles : ReturnRoles; break;
		case EFuryPlayType::Punt: Roles = bHasBall ? OffenseRoles : PuntReturnRoles; break;
		case EFuryPlayType::FieldGoal:
		case EFuryPlayType::ExtraPoint: Roles = bHasBall ? OffenseRoles : BlockRoles; break;
		default: Roles = bHasBall ? OffenseRoles : DefenseRoles; break;
		}

		int32 Seated[MaxSeats];
		int32 Count = 0;
		for (int32 i = 0; i < MaxSeats; ++i)
		{
			if (Seats[i].bActive && Seats[i].Team == Team)
			{
				Seated[Count++] = i;
			}
			else if (Seats[i].Team == Team)
			{
				Seats[i].Player = INDEX_NONE;
			}
		}
		for (int32 k = 0; k < Count; ++k)
		{
			// Rotate with the team's possessions so the quarterback job (and the rest) gets shared around.
			const int32 Role = Roles[(k + Count - TeamDrives[Team] % Count) % Count];
			const int32 Index = Global(Team, Role);
			Seats[Seated[k]].Player = Index;
			Players[Index].Seat = Seated[k];
		}
	}
}

void FFurySim::SetupKickoff()
{
	bool bOffenseUnit[2] = { false, false };
	bOffenseUnit[1 - KickingTeam] = true;
	PlaceUnits(bOffenseUnit);

	const int32 Kick = KickingTeam, Receive = 1 - KickingTeam;
	const float KD = Dir(Kick);
	const float SpotX = WorldX(Kick, KickFromYard);
	LosX = SpotX;
	BallY = 0.f;
	bHaveOffPlay = bHaveDefPlay = false;

	static const float CoverLane[TeamSize] = { 0.f, -21.f, -13.f, -5.f, 5.f, 13.f, 21.f };
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& P = Players[Global(Kick, Slot)];
		P.Job = FFuryJobSpec();
		P.Path.Reset();
		if (Slot == 0)
		{
			P.Job.Job = EFuryJob::Kicker;
			P.Home = FVector2D(SpotX - KD * 3.6f * Yard, 0.f);
		}
		else
		{
			P.Job.Job = EFuryJob::Cover;
			P.Home = FVector2D(SpotX - KD * 1.2f * Yard, CoverLane[Slot] * Yard);
		}
	}
	// Receiving team: four up front, two in the middle, one deep.
	static const FVector2D ReturnSpot[TeamSize] = {
		FVector2D(13.f, -17.f), FVector2D(13.f, -6.f), FVector2D(13.f, 6.f), FVector2D(13.f, 17.f),
		FVector2D(42.f, -9.f), FVector2D(42.f, 9.f), FVector2D(60.f, 0.f) };
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& P = Players[Global(Receive, Slot)];
		P.Job = FFuryJobSpec();
		P.Path.Reset();
		P.Job.Job = Slot == 6 ? EFuryJob::Returner : EFuryJob::ReturnBlock;
		P.Home = ClampToField(FVector2D(SpotX + KD * ReturnSpot[Slot].X * Yard, ReturnSpot[Slot].Y * Yard), 150.f);
	}

	Ball = FFuryBall();
	Ball.State = EFuryBallState::Tee;
	Ball.Pos = FVector(SpotX, 0.f, 14.f);
	for (FFurySimPlayer& P : Players)
	{
		P.bHasBall = false;
		P.PassIcon = 0;
		P.Mark = INDEX_NONE;
	}
	AssignSeats();
}

void FFurySim::SetupPlay()
{
	bool bOffenseUnit[2] = { false, false };
	bOffenseUnit[Offense] = true;
	PlaceUnits(bOffenseUnit);
	const int32 Def = Defense();
	const float D = OffenseDir();

	// Offense: spots, jobs and world-space paths.
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& P = Players[Global(Offense, Slot)];
		const FVector2D Spot = CurrentOff.Spot[Slot];
		P.Home = ClampToField(ToWorld(Spot), 120.f);
		P.Job = CurrentOff.Job[Slot];
		P.Path.Reset();
		const float Inward = Spot.Y > 0.f ? -1.f : 1.f;     // play-space direction toward the middle
		for (const FVector2D& Step : P.Job.Path)
		{
			const FVector2D Offset(Step.X, P.Job.bInward ? Step.Y * Inward : Step.Y);
			P.Path.Add(ClampToField(P.Home + FVector2D(D * Offset.X * Yard, D * Offset.Y * Yard), 110.f));
		}
		P.Mark = INDEX_NONE;
	}

	// Defense: spots follow the job. Man defenders line up over their man; zone defenders in their zone.
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& P = Players[Global(Def, Slot)];
		P.Job = CurrentDef.Job[Slot];
		P.Path.Reset();
		P.Mark = INDEX_NONE;
		FVector2D Spot = CurrentDef.Spot[Slot];
		if (P.Job.Job == EFuryJob::Man && P.Job.Target != INDEX_NONE)
		{
			const FVector2D Receiver = CurrentOff.Spot[P.Job.Target];
			const float Shade = Receiver.Y > 0.f ? -0.7f : 0.7f;
			Spot = FVector2D(FMath::Max(P.Job.Cushion + 0.4f, 1.2f), Receiver.Y * (Receiver.X < -2.f ? 0.6f : 1.f) + Shade);
			P.Mark = Global(Offense, P.Job.Target);
		}
		// Never crowd the goal line from inside the end zone's back wall.
		P.Home = ClampToField(ToWorld(Spot), 120.f);
	}

	Ball = FFuryBall();
	Ball.State = EFuryBallState::Tee;
	Ball.Pos = FVector(LosX, BallY, 12.f);
	for (FFurySimPlayer& P : Players)
	{
		P.bHasBall = false;
		P.PassIcon = 0;
	}

	// Pass icons for the three eligible receivers, ordered the way they appear on screen:
	// the far sideline (-Y) is the top of the picture.
	if (PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint)
	{
		int32 Order[3] = { 4, 5, 6 };
		Algo::Sort(Order, [this](int32 A, int32 B) { return Players[Global(Offense, A)].Home.Y < Players[Global(Offense, B)].Home.Y; });
		for (int32 i = 0; i < 3; ++i)
		{
			Players[Global(Offense, Order[i])].PassIcon = static_cast<uint8>(i + 1);
		}
	}
	AssignSeats();
}

// ---------------------------------------------------------------------------------------------
// Starting each kind of play
// ---------------------------------------------------------------------------------------------

void FFurySim::BeginKickoff(int32 Kicker, float FromYard)
{
	PlayType = EFuryPlayType::Kickoff;
	KickingTeam = Kicker;
	Offense = 1 - Kicker;
	BallTeam = Kicker;
	KickFromYard = FromYard;
	Down = 1;
	SetupKickoff();
	FirstDownX = LosX;
	Enter(EFuryPhase::Lineup);
	Emit(EFuryEvent::PlayStart, Kicker);
}

void FFurySim::BeginScrimmage(int32 NewOffense, float NewLosX, float NewBallY, bool bFirstDown)
{
	if (NewOffense != Offense || PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt)
	{
		++DriveCount;
		++TeamDrives[NewOffense];
	}
	Offense = NewOffense;
	BallTeam = NewOffense;
	PlayType = EFuryPlayType::Scrimmage;
	const float D = OffenseDir();
	// Keep the ball between the one-yard lines and between the hash marks.
	LosX = D * FMath::Clamp(NewLosX * D, -GoalX + Yard, GoalX - Yard);
	BallY = FMath::Clamp(NewBallY, -HashY, HashY);
	if (bFirstDown)
	{
		Down = 1;
		FirstDownX = D * FMath::Min(LosX * D + FirstDownYards * Yard, GoalX);
	}
	BeginPlaySelect();
}

void FFurySim::BeginPlaySelect()
{
	for (int32 Team = 0; Team < 2; ++Team)
	{
		FFuryPick& Pick = Picks[Team];
		Pick.bLocked = false;
		Pick.Play = INDEX_NONE;
		Pick.bFlip = false;
		Pick.Page = 0;
		Pick.Cursor = 4;
		Pick.CpuDelay = RandRange(0.7f, 1.5f);
	}
	SelectTimer = SelectSeconds;
	bHaveOffPlay = bHaveDefPlay = false;

	// Huddles: offense a few yards behind the ball, defense a few yards beyond it.
	const float D = OffenseDir();
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		const bool bOff = P.Team == Offense;
		const float Angle = UE_TWO_PI * P.Slot / TeamSize;
		const FVector2D Centre(LosX + D * (bOff ? -7.f : 6.f) * Yard, BallY);
		P.Home = ClampToField(Centre + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * 190.f, 150.f);
		P.bHasBall = false;
	}
	Ball.State = EFuryBallState::Tee;
	Ball.Holder = INDEX_NONE;
	Ball.Pos = FVector(LosX, BallY, 12.f);
	Enter(EFuryPhase::PlaySelect);
}

// ---------------------------------------------------------------------------------------------
// Choosing plays
// ---------------------------------------------------------------------------------------------

bool FFurySim::ChooseSituationalKick(FFuryPick& Pick) const
{
	const float ToGo = YardsToGo();
	const float Line = YardLine(Offense, LosX);
	const int32 Lead = Teams[Offense].Score - Teams[Defense()].Score;
	const bool bLate = Quarter >= 4 && Clock < 45.f;
	const bool bDesperate = bLate && Lead < 0;

	if (PlayType != EFuryPlayType::TwoPoint && Down == 4)
	{
		const float KickYards = (100.f - Line) + 17.f;
		const bool bInRange = KickYards <= 52.f;
		const bool bGoForIt = bDesperate && Lead < -3;
		if (bInRange && !bGoForIt && (ToGo > 2.f || Lead >= -3))
		{
			Pick.Page = 2; Pick.Cursor = 1; Pick.Play = -3;
			return true;
		}
		if (!bDesperate && ToGo > 7.f && Line < 62.f)
		{
			Pick.Page = 2; Pick.Cursor = 0; Pick.Play = -2;
			return true;
		}
	}
	// Last-second field goal to win or tie.
	if (PlayType != EFuryPlayType::TwoPoint && bLate && Clock < 8.f && Lead <= 0 && Lead >= -3 && (100.f - Line) + 17.f <= 55.f)
	{
		Pick.Page = 2; Pick.Cursor = 1; Pick.Play = -3;
		return true;
	}
	return false;
}

void FFurySim::CpuPickOffense(FFuryPick& Pick)
{
	Pick.bFlip = Chance(0.5f);
	if (ChooseSituationalKick(Pick)) { return; }
	const float ToGo = YardsToGo();
	const float Line = YardLine(Offense, LosX);
	const bool bDesperate = Quarter >= 4 && Clock < 45.f && Teams[Offense].Score < Teams[Defense()].Score;
	const TArray<FFuryOffPlay>& All = FuryPlaybook::Offense();
	TArray<int32> Pool;
	const float RunChance = bDesperate ? 0.05f : ToGo <= 5.f ? 0.45f : ToGo > 20.f ? 0.12f : 0.26f;
	const bool bWantRun = Chance(RunChance);
	for (int32 i = 0; i < All.Num(); ++i)
	{
		const bool bRun = All[i].Kind == EFuryPlayKind::Run;
		if (bRun != bWantRun)
		{
			continue;
		}
		const FString& Name = All[i].Name;
		int32 Weight = 2;
		const bool bDeep = Name == TEXT("SKYLINE") || Name == TEXT("POST MASTER") || Name == TEXT("DAGGER") || Name == TEXT("HAIL FURY") || Name == TEXT("PLAY ACTION");
		const bool bQuick = Name == TEXT("SLANT STORM") || Name == TEXT("QUICK HITCH") || Name == TEXT("MESH") || Name == TEXT("CURL UP");
		if (!bRun)
		{
			if (ToGo > 18.f) { Weight = bDeep ? 5 : bQuick ? 1 : 3; }
			else if (ToGo < 8.f) { Weight = bQuick ? 5 : bDeep ? 1 : 3; }
			if (Name == TEXT("HAIL FURY")) { Weight = (bDesperate || ToGo > 28.f) ? 4 : 0; }
			if (100.f - Line < 12.f && bDeep) { Weight = 0; }      // no room for bombs at the goal line
		}
		for (int32 k = 0; k < Weight; ++k)
		{
			Pool.Add(i);
		}
	}
	const int32 Choice = Pool.Num() > 0 ? Pool[Random.RandRange(0, Pool.Num() - 1)] : Random.RandRange(0, All.Num() - 1);
	Pick.Page = Choice / FuryPlaybook::PlaysPerPage;
	Pick.Cursor = Choice % FuryPlaybook::PlaysPerPage;
	Pick.Play = Choice;
}

void FFurySim::CpuPickDefense(FFuryPick& Pick)
{
	const float ToGo = YardsToGo();
	const float Line = YardLine(Offense, LosX);
	// Order matches FuryPlaybook::Defense().
	enum { AllOut, PressMan, ZoneBlanket, PicketFence, BaseMan, CornerFire, SpyGame, DoubleTrouble, Prevent };
	int32 Weight[9] = { 2, 3, 3, 3, 4, 2, 2, 2, 0 };
	if (ToGo > 22.f) { Weight[ZoneBlanket] = 6; Weight[Prevent] = 3; Weight[PicketFence] = 1; Weight[PressMan] = 1; }
	if (ToGo < 7.f) { Weight[PicketFence] = 6; Weight[PressMan] = 5; Weight[AllOut] = 4; Weight[ZoneBlanket] = 1; }
	if (100.f - Line < 10.f) { Weight[PressMan] = 6; Weight[AllOut] = 5; Weight[Prevent] = 0; Weight[ZoneBlanket] = 1; }
	if (Quarter >= 4 && Clock < 20.f && Teams[Defense()].Score > Teams[Offense].Score) { Weight[Prevent] = 9; }
	// Better computer teams blitz more.
	Weight[AllOut] += FMath::RoundToInt32(CpuSkill * 2.f);
	Weight[CornerFire] += FMath::RoundToInt32(CpuSkill * 2.f);

	int32 Total = 0;
	for (const int32 W : Weight) { Total += W; }
	int32 Roll = Random.RandRange(0, Total - 1);
	int32 Choice = 0;
	for (int32 i = 0; i < 9; ++i)
	{
		if (Roll < Weight[i]) { Choice = i; break; }
		Roll -= Weight[i];
	}
	Pick.Page = 0;
	Pick.Cursor = Choice;
	Pick.Play = Choice;
	Pick.bFlip = Chance(0.5f);
}

void FFurySim::StepPlaySelect(float Dt, const FFurySeatInput* Inputs)
{
	SelectTimer -= Dt;
	for (int32 Team = 0; Team < 2; ++Team)
	{
		FFuryPick& Pick = Picks[Team];
		if (Pick.bLocked)
		{
			continue;
		}
		const bool bOff = Team == Offense;
		const int32 Seat = Captain(Team);
		if (Seat == INDEX_NONE)
		{
			Pick.CpuDelay -= Dt;
			if (Pick.CpuDelay <= 0.f)
			{
				if (bOff) { CpuPickOffense(Pick); } else { CpuPickDefense(Pick); }
				Pick.bLocked = true;
				Emit(EFuryEvent::PlayPicked, Team);
			}
			continue;
		}

		const FFurySeatInput& In = Inputs[Seat];
		int32 Col = Pick.Cursor % 3, Row = Pick.Cursor / 3;
		Col = (Col + In.NavX + 3) % 3;
		Row = (Row - In.NavY + 3) % 3;
		Pick.Cursor = Row * 3 + Col;
		if (bOff)
		{
			const int32 Pages = NumOffensePages();
			if (In.RB) { Pick.Page = (Pick.Page + 1) % Pages; }
			if (In.LB) { Pick.Page = (Pick.Page + Pages - 1) % Pages; }
			if (!OffenseChoice(Pick.Page, Pick.Cursor))
			{
				// Empty cell (the kicking page is short): fall back to the first play on the page.
				Pick.Cursor = OffenseChoice(Pick.Page, 0) ? 0 : 4;
				if (!OffenseChoice(Pick.Page, Pick.Cursor)) { Pick.Page = 0; }
			}
		}
		if (In.X)
		{
			Pick.bFlip = !Pick.bFlip;
		}
		const bool bTimeUp = SelectTimer <= 0.f;
		if ((In.A && PhaseTime > 0.3f) || bTimeUp)
		{
			if (bOff)
			{
				const FFuryOffPlay* Choice = OffenseChoice(Pick.Page, Pick.Cursor);
				Pick.Play = !Choice ? 0 : Pick.Page == 2 ? (Pick.Cursor == 0 ? -2 : -3) : Pick.Page * FuryPlaybook::PlaysPerPage + Pick.Cursor;
			}
			else
			{
				Pick.Play = Pick.Cursor;
			}
			Pick.bLocked = true;
			Emit(EFuryEvent::PlayPicked, Team);
		}
	}

	if (!Picks[0].bLocked || !Picks[1].bLocked)
	{
		return;
	}

	// Both sides are in: build the play.
	const FFuryPick& Off = Picks[Offense];
	const FFuryPick& Def = Picks[Defense()];
	if (Off.Play == -2 || Off.Play == -3)
	{
		CurrentOff = Off.Play == -2 ? FuryPlaybook::Punt() : FuryPlaybook::FieldGoal();
		CurrentDef = FuryPlaybook::KickBlock();
		PlayType = Off.Play == -2 ? EFuryPlayType::Punt : EFuryPlayType::FieldGoal;
	}
	else
	{
		const FFuryOffPlay& Base = FuryPlaybook::Offense()[FMath::Clamp(Off.Play, 0, FuryPlaybook::Offense().Num() - 1)];
		CurrentOff = Off.bFlip ? FuryPlaybook::Flip(Base) : Base;
		const FFuryDefPlay& DefBase = FuryPlaybook::Defense()[FMath::Clamp(Def.Play, 0, FuryPlaybook::Defense().Num() - 1)];
		CurrentDef = Def.bFlip ? FuryPlaybook::Flip(DefBase) : DefBase;
	}
	bHaveOffPlay = bHaveDefPlay = true;
	SetupPlay();
	Enter(EFuryPhase::Lineup);
	Emit(EFuryEvent::PlayStart, Offense);
}

void FFurySim::StepPatSelect(float Dt, const FFurySeatInput* Inputs)
{
	const int32 Seat = Captain(ScoringTeam);
	bool bDecided = false;
	if (Seat == INDEX_NONE)
	{
		if (PhaseTime > 0.9f)
		{
			// Go for two when it turns a deficit into a tie or a lead into a touchdown-plus cushion.
			const int32 Lead = Teams[ScoringTeam].Score - Teams[1 - ScoringTeam].Score;
			PatChoice = (Lead == -2 || Lead == -5 || Lead == 1 || (Quarter >= 4 && Lead == -1)) ? 1 : (Chance(0.08f) ? 1 : 0);
			bDecided = true;
		}
	}
	else
	{
		const FFurySeatInput& In = Inputs[Seat];
		if (In.NavX != 0 || In.NavY != 0)
		{
			PatChoice = 1 - PatChoice;
		}
		bDecided = (In.A && PhaseTime > 0.4f) || PhaseTime > 8.f;
	}
	if (!bDecided)
	{
		return;
	}

	Offense = ScoringTeam;
	BallTeam = ScoringTeam;
	const float D = OffenseDir();
	BallY = 0.f;
	Down = 1;
	if (PatChoice == 0)
	{
		PlayType = EFuryPlayType::ExtraPoint;
		LosX = D * (GoalX - 10.f * Yard);
		FirstDownX = D * GoalX;
		CurrentOff = FuryPlaybook::FieldGoal();
		CurrentDef = FuryPlaybook::KickBlock();
		bHaveOffPlay = bHaveDefPlay = true;
		SetupPlay();
		Enter(EFuryPhase::Lineup);
		Emit(EFuryEvent::PlayStart, Offense);
	}
	else
	{
		PlayType = EFuryPlayType::TwoPoint;
		LosX = D * (GoalX - 3.f * Yard);
		FirstDownX = D * GoalX;
		BeginPlaySelect();
	}
}

// ---------------------------------------------------------------------------------------------
// Lining up and the snap
// ---------------------------------------------------------------------------------------------

void FFurySim::StepLineup(float Dt)
{
	const float D = OffenseDir();
	bool bAllSet = true;
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		if (PhaseTime <= Dt * 1.5f)
		{
			// Fresh play: everyone is on their feet, and nobody has a marathon to run to the huddle.
			P.bDown = false; P.bBusy = false; P.Engaged = INDEX_NONE; P.DownLeft = 0.f; P.Launch = FVector2D::ZeroVector; P.Height = 0.f;
			P.EvadeLeft = P.StiffLeft = P.Cooldown = P.JumpLeft = P.CatchCool = P.Burst = P.BurstCool = 0.f;
			P.bScramble = false; P.bFace = false; P.React = 0.f; P.PathIndex = 0; P.bRouteDone = false; P.bBroke = false;
			P.bPursue = false; P.ReadLeft = -1.f;
			SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
			const FVector2D Away = P.P - P.Home;
			if (Away.Size() > 6.f * Yard)
			{
				P.P = P.Home + Away.GetSafeNormal() * 6.f * Yard;
			}
		}
		const FVector2D To = P.Home - P.P;
		const float Dist = To.Size();
		if (Dist > 12.f)
		{
			bAllSet = false;
			const float Speed = FMath::Min(P.TopSpeed * 0.8f, Dist / FMath::Max(LineupSeconds - PhaseTime, 0.12f) + 120.f);
			P.V = To / Dist * Speed;
			P.P += P.V * FMath::Min(Dt, Dist / Speed);
			P.Yaw = AngleOf(P.V);
		}
		else
		{
			P.P = P.Home;
			P.V = FVector2D::ZeroVector;
		}
	}
	if (!bAllSet && PhaseTime < LineupSeconds + 0.6f)
	{
		return;
	}

	// Set: face the other side and drop into a stance.
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		P.P = P.Home;
		P.V = FVector2D::ZeroVector;
		const bool bOff = PlayType == EFuryPlayType::Kickoff ? P.Team == KickingTeam : P.Team == Offense;
		const float Facing = PlayType == EFuryPlayType::Kickoff ? Dir(P.Team) : (bOff ? D : -D);
		P.Yaw = Facing > 0.f ? 0.f : UE_PI;
		EFuryStance Stance = EFuryStance::Ready;
		if (PlayType == EFuryPlayType::Kickoff)
		{
			Stance = EFuryStance::Ready;
		}
		else if (bOff)
		{
			switch (P.Job.Job)
			{
			case EFuryJob::Passer: case EFuryJob::Keeper: Stance = EFuryStance::QB; break;
			case EFuryJob::Punter: Stance = EFuryStance::QB; break;
			case EFuryJob::Kicker: Stance = EFuryStance::Idle; break;
			case EFuryJob::Holder: Stance = EFuryStance::Ready; break;
			default: Stance = P.Slot == 1 ? EFuryStance::Center : (P.Pos == EFuryPos::OL ? EFuryStance::ThreePoint : EFuryStance::Ready); break;
			}
		}
		else
		{
			Stance = P.Pos == EFuryPos::DL ? EFuryStance::ThreePoint : EFuryStance::Ready;
		}
		SetAct(P, EFuryAct::Stand, static_cast<uint8>(Stance), 0.f, 0.f, false);
	}

	const int32 CallingTeam = PlayType == EFuryPlayType::Kickoff ? KickingTeam : Offense;
	SnapDelay = Captain(CallingTeam) == INDEX_NONE ? RandRange(1.0f, 1.9f) : 7.f;
	HutTimer = 0.35f;
	KickMeter = 0.f;
	KickAim = 0.f;
	bKickMeterLive = false;
	bKickLocked = false;
	KickSteer = FVector2D::ZeroVector;
	bBallCrossedLine = false;
	bPassThrown = false;
	bChangeOfPossession = false;
	bKickTouched = false;
	bKickPossessed = false;
	bReturnEnteredField = false;
	bFirstDownMade = false;
	PassSeat = INDEX_NONE;
	StartLosX = LosX;
	ReturnStartX = LosX;
	PlayYards = 0.f;
	LiveTime = 0.f;
	Enter(EFuryPhase::PreSnap);
}

void FFurySim::StepPreSnap(float Dt, const FFurySeatInput* Inputs)
{
	const int32 CallingTeam = PlayType == EFuryPlayType::Kickoff ? KickingTeam : Offense;
	const int32 Seat = Captain(CallingTeam);
	const bool bScrimmage = PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint;

	// The quarterback barks the count.
	if (bScrimmage)
	{
		HutTimer -= Dt;
		if (HutTimer <= 0.f)
		{
			HutTimer = RandRange(0.7f, 1.1f);
			Emit(EFuryEvent::Hut, Offense, Global(Offense, 0));
		}
	}

	// Human defenders may walk around on their side of the ball before the snap.
	if (bScrimmage)
	{
		const float D = OffenseDir();
		for (int32 SeatIndex = 0; SeatIndex < MaxSeats; ++SeatIndex)
		{
			const FFurySeat& Defender = Seats[SeatIndex];
			if (!Defender.bActive || Defender.Player == INDEX_NONE || Defender.Team == Offense)
			{
				continue;
			}
			FFurySimPlayer& P = Players[Defender.Player];
			const FFurySeatInput& In = Inputs[SeatIndex];
			const FVector2D Wish(In.Stick.X, -In.Stick.Y);
			if (Wish.SizeSquared() > 0.04f)
			{
				P.P += Wish * (P.TopSpeed * 0.6f) * Dt;
				P.P.X = D * FMath::Max(P.P.X * D, LosX * D + 1.1f * Yard);
				P.P = ClampToField(P.P, 100.f);
				P.Home = P.P;
			}
			if (In.A && PhaseTime > 0.3f)
			{
				// Cycle to the next defender no human is steering.
				for (int32 k = 1; k < TeamSize; ++k)
				{
					const int32 Next = Global(P.Team, (P.Slot + k) % TeamSize);
					if (Players[Next].Seat == INDEX_NONE)
					{
						SwitchSeat(P.Seat, Next);
						break;
					}
				}
			}
		}
	}

	bool bGo = PhaseTime >= SnapDelay;
	if (Seat != INDEX_NONE && Inputs[Seat].A && PhaseTime > 0.35f)
	{
		bGo = true;
	}
	if (!bGo)
	{
		return;
	}

	if (PlayType == EFuryPlayType::Kickoff)
	{
		for (FFurySimPlayer& P : Players)
		{
			SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
			P.React = 0.f;
			P.Think = 0.f;
		}
		StartKick(Global(KickingTeam, 0));
		Enter(EFuryPhase::Live);
		LiveTime = 0.f;
	}
	else
	{
		SnapBall();
	}
}

void FFurySim::SnapBall()
{
	Enter(EFuryPhase::Live);
	LiveTime = 0.f;
	++PlayCount;
	for (int32 Team = 0; Team < 2; ++Team) { FuryAtSnap[Team] = Teams[Team].InFury(); }
	const int32 Def = Defense();
	const int32 Centre = Global(Offense, 1);

	// Who takes the snap: the passer, punter or holder.
	int32 Taker = Global(Offense, 0);
	if (PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint)
	{
		Taker = Global(Offense, 6);
	}
	SetAct(Players[Centre], EFuryAct::Snap, 0, 0.4f, 0.1f, true);
	Ball.State = EFuryBallState::Snap;
	Ball.Holder = INDEX_NONE;
	Ball.Target = Taker;
	Ball.From = FVector(LosX, BallY, 25.f);
	Ball.To = FVector(Players[Taker].P.X, Players[Taker].P.Y, PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint ? 30.f : 105.f);
	Ball.Time = 0.f;
	Ball.Duration = 0.24f + FVector::Dist2D(Ball.From, Ball.To) / 3600.f;
	Ball.Pos = Ball.From;
	Emit(EFuryEvent::Snap, Offense, Centre);

	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		if (i == Centre)
		{
			continue;
		}
		const bool bOff = P.Team == Offense;
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
		P.PathIndex = 0;
		P.bRouteDone = false;
		P.bBroke = false;
		P.Think = RandRange(0.f, 0.2f);
		const float DefenseRating = (TeamInfo(Def).Defense - 3) * 0.02f;
		P.React = bOff ? RandRange(0.f, 0.06f) + P.Job.Delay : FMath::Max(0.04f, RandRange(0.1f, 0.24f) - DefenseRating - CpuSkill * 0.05f);
		if (!bOff && P.Job.Job == EFuryJob::Blitz)
		{
			P.React += P.Job.Delay;
		}
		// A play-action fake holds the linebacker and the safety for a beat.
		if (!bOff && CurrentOff.bPlayAction && (P.Slot == 3 || P.Slot == 6) && P.Job.Job != EFuryJob::Blitz && P.Seat == INDEX_NONE)
		{
			P.React += RandRange(0.45f, 0.75f) * (1.f - CpuSkill * 0.4f);
		}
	}

	// Press coverage: a successful jam holds the receiver up at the line.
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& Corner = Players[Global(Def, Slot)];
		if (Corner.Job.Job == EFuryJob::Man && Corner.Job.bPress && Corner.Mark != INDEX_NONE && Chance(0.6f))
		{
			Players[Corner.Mark].React += RandRange(0.35f, 0.6f);
			SetAct(Corner, EFuryAct::Shove, 0, 0.4f, 0.12f, false);
		}
	}

	if (PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint)
	{
		bKickMeterLive = true;
		StartKick(Global(Offense, 0));
	}
	PairBlockers();
}

// ---------------------------------------------------------------------------------------------
// Ending a play, downs and scoring
// ---------------------------------------------------------------------------------------------

void FFurySim::DownBall(float SpotX, float SpotY, const TCHAR* Title, const FString& Detail, int32 Team)
{
	if (Phase != EFuryPhase::Live)
	{
		return;
	}
	DeadSpotX = SpotX;
	DeadSpotY = SpotY;
	EndPlay(Title, Detail, Team);
}

void FFurySim::EndPlay(const TCHAR* Title, const FString& Detail, int32 Team)
{
	ResultTitle = Title;
	ResultDetail = Detail;
	ResultTeam = Team;
	BeginAfterWhistle(EFuryPhase::Dead, FVector2D(DeadSpotX, DeadSpotY));
}

void FFurySim::BeginAfterWhistle(EFuryPhase NewPhase, FVector2D Spot)
{
	bKickMeterLive = false;
	ReadySeats = 0;
	WhistleFocus = Spot;
	Ball.State = EFuryBallState::Dead;
	Ball.Holder = Ball.Target = INDEX_NONE;
	Ball.Pos = FVector(Spot, 10.f);
	Ball.Vel = FVector::ZeroVector;
	for (FFurySimPlayer& P : Players)
	{
		P.bHasBall = false;
		if (P.Engaged != INDEX_NONE) { Disengage(Global(P.Team, P.Slot)); }
		if (P.bDown) { P.DownLeft = FMath::Min(P.DownLeft, 2.2f); }
		P.Think = RandRange(0.4f, 1.4f);
		P.Mark = INDEX_NONE;
	}
	Emit(EFuryEvent::Whistle);
	Enter(NewPhase);
}

void FFurySim::Score(int32 Team, int32 Points, int32 PlayerIndex)
{
	Teams[Team].Score += Points;
	Teams[Team].ScoreByQuarter[FMath::Clamp(Quarter - 1, 0, 4)] += Points;
	ScoringTeam = Team;
	Scorer = PlayerIndex;
}

/** After a score (and its conversion): kick off, unless the clock or overtime says otherwise. */
void FFurySim::NextAfterScore()
{
	if (bOvertime)
	{
		Enter(EFuryPhase::GameOver);
		Emit(EFuryEvent::GameOver, Winner());
		return;
	}
	if (bClockExpired)
	{
		EndQuarter();
		if (Phase == EFuryPhase::GameOver || Quarter == 3 || bOvertime)
		{
			return;      // the new half / overtime starts with its own kickoff
		}
	}
	PendingScoreTeam = INDEX_NONE;
	BeginKickoff(ScoringTeam, 35.f);
	if (bClockExpired)
	{
		// A quarter break is showing; the kickoff is already set up behind it.
		bClockExpired = false;
		Enter(EFuryPhase::Break);
	}
}

void FFurySim::ResolveDown(float SpotX, float SpotY)
{
	// Called when the aftermath of a play is over and the next one has to be set up.
	if (PlayType == EFuryPlayType::Scrimmage)
	{
		TickFuryAfterPlay();
	}
	const float D = OffenseDir();
	const bool bScoreTry = PlayType == EFuryPlayType::ExtraPoint || PlayType == EFuryPlayType::TwoPoint;
	if (bScoreTry)
	{
		NextAfterScore();
		return;
	}

	enum class ENext { Scrimmage, Kickoff } Next = ENext::Scrimmage;
	int32 NextOffense = Offense;
	float NextX = SpotX, NextY = SpotY;
	bool bFirst = false;
	int32 NextKicker = 0;
	float NextKickFrom = 35.f;

	if (PendingScoreTeam != INDEX_NONE && bOvertime)
	{
		// Sudden death: a field goal or a safety wins it just as surely as a touchdown.
		PendingScoreTeam = INDEX_NONE;
		Enter(EFuryPhase::GameOver);
		Emit(EFuryEvent::GameOver, Winner());
		return;
	}
	if (PendingScoreTeam != INDEX_NONE)
	{
		// Field goal or safety already on the board.
		Next = ENext::Kickoff;
		NextKicker = ResultTitle == TEXT("SAFETY") ? 1 - PendingScoreTeam : PendingScoreTeam;
		NextKickFrom = ResultTitle == TEXT("SAFETY") ? 20.f : 35.f;
		PendingScoreTeam = INDEX_NONE;
	}
	else if (ResultTitle == TEXT("TOUCHBACK"))
	{
		NextOffense = ResultTeam;
		NextX = WorldX(ResultTeam, 25.f);
		NextY = 0.f;
		bFirst = true;
	}
	else if (ResultTitle == TEXT("NO GOOD"))
	{
		// Missed field goal: the other side takes over where the ball was snapped, no closer than its 20.
		NextOffense = Defense();
		NextX = Dir(NextOffense) * FMath::Max(StartLosX * Dir(NextOffense), -GoalX + 20.f * Yard);
		NextY = 0.f;
		bFirst = true;
	}
	else if (PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt || bChangeOfPossession)
	{
		NextOffense = BallTeam;
		bFirst = true;
	}
	else if (ResultTitle == TEXT("INCOMPLETE"))
	{
		NextX = StartLosX;
		NextY = BallY;
		++Down;
	}
	else
	{
		// An ordinary play from scrimmage: did it move the chains?
		if ((SpotX - FirstDownX) * D >= 0.f)
		{
			bFirst = true;
			++Teams[Offense].FirstDowns;
			Emit(EFuryEvent::FirstDown, Offense);
			AddFury(Offense, 0.04f);
		}
		else
		{
			++Down;
		}
	}

	if (Next == ENext::Scrimmage && !bFirst && Down > 4)
	{
		Emit(EFuryEvent::TurnoverOnDowns, Defense());
		AddFury(Defense(), 0.2f);
		NextOffense = Defense();
		bFirst = true;
	}

	if (bClockExpired)
	{
		const int32 EndedQuarter = Quarter;
		EndQuarter();
		if (Phase == EFuryPhase::GameOver || EndedQuarter == 2 || bOvertime)
		{
			return;
		}
		// Quarters one and three: play simply carries on after the break.
		bClockExpired = false;
		if (Next == ENext::Kickoff) { BeginKickoff(NextKicker, NextKickFrom); }
		else { BeginScrimmage(NextOffense, NextX, NextY, bFirst); }
		Enter(EFuryPhase::Break);
		return;
	}

	if (Next == ENext::Kickoff)
	{
		BeginKickoff(NextKicker, NextKickFrom);
	}
	else
	{
		BeginScrimmage(NextOffense, NextX, NextY, bFirst);
	}
}

void FFurySim::EndQuarter()
{
	Emit(EFuryEvent::QuarterEnd, INDEX_NONE, INDEX_NONE, INDEX_NONE, static_cast<float>(Quarter));
	if (Quarter == 2)
	{
		Quarter = 3;
		Clock = QuarterLength;
		bClockExpired = false;
		Emit(EFuryEvent::Halftime);
		// The side that received the opening kick kicks off the second half.
		BeginKickoff(1 - OpeningKicker, 35.f);
		Enter(EFuryPhase::Break);
		return;
	}
	if (Quarter >= 4)
	{
		if (Teams[0].Score != Teams[1].Score)
		{
			Enter(EFuryPhase::GameOver);
			Emit(EFuryEvent::GameOver, Winner());
			return;
		}
		// Sudden death: first score wins, no clock.
		bOvertime = true;
		Quarter = 5;
		Clock = 0.f;
		bClockExpired = false;
		Emit(EFuryEvent::Overtime);
		BeginKickoff(Random.RandRange(0, 1), 35.f);
		Enter(EFuryPhase::Break);
		return;
	}
	++Quarter;
	Clock = QuarterLength;
}

void FFurySim::StepAfterWhistle(const FFurySeatInput* Inputs)
{
	uint8 Active = 0;
	for (int32 i = 0; i < MaxSeats; ++i)
	{
		if (!Seats[i].bActive) { continue; }
		Active |= 1u << i;
		if (PhaseTime > 0.5f && Inputs[i].A) { ReadySeats |= 1u << i; }
	}
	if (PhaseTime < AfterWhistleSeconds && !(Active && (ReadySeats & Active) == Active)) { return; }
	if (Phase == EFuryPhase::Dead) { ResolveDown(DeadSpotX, DeadSpotY); }
	else { FinishCelebration(); }
}

void FFurySim::FinishCelebration()
{
	if (PlayType == EFuryPlayType::Scrimmage)
	{
		TickFuryAfterPlay();
	}
	if (bOvertime)
	{
		Enter(EFuryPhase::GameOver);
		Emit(EFuryEvent::GameOver, Winner());
		return;
	}
	PatChoice = 0;
	Enter(EFuryPhase::PatSelect);
}

void FFurySim::StepBreak(float Dt)
{
	const float Length = Quarter == 3 && Clock >= QuarterLength - 0.01f && PlayType == EFuryPlayType::Kickoff ? 7.f : 3.5f;
	if (PhaseTime >= Length)
	{
		// The next play was set up before the break; pick it up where it stood.
		if (PlayType == EFuryPlayType::Kickoff)
		{
			Enter(EFuryPhase::Lineup);
		}
		else
		{
			Enter(EFuryPhase::PlaySelect);
			SelectTimer = SelectSeconds;
		}
	}
}

// ---------------------------------------------------------------------------------------------
// The step
// ---------------------------------------------------------------------------------------------

void FFurySim::Step(float Dt, const FFurySeatInput* Inputs)
{
	PhaseTime += Dt;
	switch (Phase)
	{
	case EFuryPhase::PlaySelect:
		StepLive(Dt, Inputs);          // players drift to their huddles behind the play menu
		StepPlaySelect(Dt, Inputs);
		break;
	case EFuryPhase::Lineup:
		for (FFurySimPlayer& P : Players) { P.ActTime += Dt; }
		StepLineup(Dt);
		break;
	case EFuryPhase::PreSnap:
		for (FFurySimPlayer& P : Players) { P.ActTime += Dt; }
		StepPreSnap(Dt, Inputs);
		break;
	case EFuryPhase::Live:
		StepLive(Dt, Inputs);
		break;
	case EFuryPhase::Dead:
	case EFuryPhase::Celebrate:
		StepLive(Dt, Inputs);
		StepAfterWhistle(Inputs);
		break;
	case EFuryPhase::PatSelect:
		StepLive(Dt, Inputs);
		if (Phase == EFuryPhase::PatSelect) { StepPatSelect(Dt, Inputs); }
		break;
	case EFuryPhase::Break:
		StepLive(Dt, Inputs);
		if (Phase == EFuryPhase::Break) { StepBreak(Dt); }
		break;
	case EFuryPhase::GameOver:
		StepLive(Dt, Inputs);
		break;
	}
}
