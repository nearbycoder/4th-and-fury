#include "FurySim.h"

// The live action: human control, movement, blocking, the ball, tackles and the rules that end a play.

namespace
{
	using namespace Fury;

	constexpr float Accel = 3400.f;          // cm/s^2: athletes hit top speed in about a quarter second
	constexpr float Decel = 4800.f;
	constexpr float TurnRate = 13.f;         // rad/s
	constexpr float TurboBoost = 1.16f;       // a human holding turbo
	constexpr float BurstBoost = 1.12f;       // a computer player's equivalent, used in spurts
	constexpr float FuryBoost = 1.1f;
	constexpr float Gravity = 980.f;
	constexpr float CatchReach = 92.f;
	constexpr float BallRadius = 9.f;

	FVector2D StickToWorld(const FVector2D& Stick)
	{
		// Screen right is +X; screen up is the far sideline, which is -Y.
		return FVector2D(Stick.X, -Stick.Y);
	}

	float ActDuration(EFuryFall Fall)
	{
		switch (Fall)
		{
		case EFuryFall::Front: return 0.62f;
		case EFuryFall::Flip: return 0.9f;
		case EFuryFall::Spin: return 0.82f;
		default: return 0.7f;
		}
	}

	// Blender rig measurements in field centimetres. The down loops put the chest
	// 61 cm from the actor root. The elbow key is 113 cm forward and 17 cm left.
	FVector2D FloorChest(const FFurySimPlayer& P)
	{
		const bool bFront = P.Act == EFuryAct::Hit
			? P.Variant == uint8(EFuryFall::Front) || P.Variant == uint8(EFuryFall::Spin)
			: P.Variant == 1;
		return P.P + FromAngle(P.Yaw) * (bFront ? 61.f : -61.f);
	}

	FVector2D ElbowOffset(float Yaw)
	{
		const FVector2D F = FromAngle(Yaw);
		return F * 113.f + FVector2D(F.Y, -F.X) * 17.f;
	}

	bool OnFloor(const FFurySimPlayer& P)
	{
		return P.Act == EFuryAct::Down || (P.Act == EFuryAct::Hit && P.ActTime >= P.ActLength * 0.78f);
	}
}

// ---------------------------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------------------------

void FFurySim::SetAct(FFurySimPlayer& Player, EFuryAct Act, uint8 Variant, float Length, float Key, bool bBusy)
{
	Player.Act = Act;
	Player.Variant = Variant;
	++Player.ActSerial;
	Player.ActTime = 0.f;
	Player.ActLength = Length;
	Player.ActKey = Key;
	Player.bKeyDone = Key <= 0.f;
	Player.bBusy = bBusy;
	Player.bDiveSpent = false;
}

float FFurySim::MaxSpeed(const FFurySimPlayer& Player, bool bTurbo) const
{
	float Speed = Player.TopSpeed;
	if (Teams[Player.Team].InFury())
	{
		Speed *= FuryBoost;
	}
	if (bTurbo || Player.Burst > 0.f)
	{
		Speed *= bTurbo ? TurboBoost : BurstBoost;
	}
	return Speed;
}

int32 FFurySim::NearestOpponent(int32 Index, float MaxDist, bool bUprightOnly) const
{
	const FFurySimPlayer& Me = Players[Index];
	int32 Best = INDEX_NONE;
	float BestDist = MaxDist * MaxDist;
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		const FFurySimPlayer& Other = Players[i];
		if (Other.Team == Me.Team || (bUprightOnly && Other.bDown))
		{
			continue;
		}
		const float Dist = FVector2D::DistSquared(Me.P, Other.P);
		if (Dist < BestDist)
		{
			BestDist = Dist;
			Best = i;
		}
	}
	return Best;
}

int32 FFurySim::ClosestToBall(int32 Team, bool bExcludeHumans, int32 Exclude) const
{
	FVector2D Point(Ball.Pos.X, Ball.Pos.Y);
	if (Ball.State == EFuryBallState::Pass || Ball.State == EFuryBallState::Kick)
	{
		Point = Ball.Land();
	}
	int32 Best = INDEX_NONE;
	float BestDist = TNumericLimits<float>::Max();
	for (int32 Slot = 0; Slot < TeamSize; ++Slot)
	{
		const int32 Index = Global(Team, Slot);
		const FFurySimPlayer& P = Players[Index];
		if (Index == Exclude || (bExcludeHumans && P.Seat != INDEX_NONE))
		{
			continue;
		}
		const float Dist = FVector2D::DistSquared(P.P, Point) + (P.bDown ? 1.e9f : 0.f) + (P.Engaged != INDEX_NONE ? 4.e5f : 0.f);
		if (Dist < BestDist)
		{
			BestDist = Dist;
			Best = Index;
		}
	}
	return Best;
}

void FFurySim::SwitchSeat(int32 SeatIndex, int32 NewPlayer)
{
	if (NewPlayer == INDEX_NONE || !Seats[SeatIndex].bActive)
	{
		return;
	}
	const int32 Old = Seats[SeatIndex].Player;
	if (Old != INDEX_NONE)
	{
		Players[Old].Seat = INDEX_NONE;
	}
	if (Players[NewPlayer].Seat != INDEX_NONE)
	{
		Seats[Players[NewPlayer].Seat].Player = INDEX_NONE;
	}
	Players[NewPlayer].Seat = SeatIndex;
	Seats[SeatIndex].Player = NewPlayer;
	Seats[SeatIndex].Idle = 0.f;
}

/** Whoever ends up with the ball should be in a human's hands if that team has a human. */
void FFurySim::ControlFollowsBall(int32 NewHolder)
{
	const FFurySimPlayer& Holder = Players[NewHolder];
	if (Holder.Seat != INDEX_NONE)
	{
		return;
	}
	// Prefer the human who just got rid of the ball; otherwise the team's first human.
	int32 Choice = INDEX_NONE;
	if (Ball.Thrower != INDEX_NONE && Players[Ball.Thrower].Team == Holder.Team && Players[Ball.Thrower].Seat != INDEX_NONE)
	{
		Choice = Players[Ball.Thrower].Seat;
	}
	for (int32 i = 0; i < MaxSeats && Choice == INDEX_NONE; ++i)
	{
		if (Seats[i].bActive && Seats[i].Team == Holder.Team)
		{
			Choice = i;
		}
	}
	if (Choice != INDEX_NONE)
	{
		SwitchSeat(Choice, NewHolder);
	}
}

void FFurySim::GiveBall(int32 To)
{
	for (FFurySimPlayer& P : Players)
	{
		P.bHasBall = false;
	}
	FFurySimPlayer& Holder = Players[To];
	Holder.bHasBall = true;
	Ball.State = EFuryBallState::Held;
	Ball.Holder = To;
	Ball.Vel = FVector::ZeroVector;
	const bool bKickPlay = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;
	if (Holder.Team != BallTeam || (bKickPlay && !bKickPossessed))
	{
		ReturnStartX = Holder.P.X;
		bReturnEnteredField = Holder.P.X * Dir(Holder.Team) > -GoalX;
	}
	if (Holder.Team != BallTeam)
	{
		// On a kick the ball simply belongs to whoever ends up with it; otherwise this is a turnover.
		if (!bKickPlay)
		{
			bChangeOfPossession = true;
		}
		BallTeam = Holder.Team;
	}
	if (bKickPlay)
	{
		bKickPossessed = true;
	}
	ControlFollowsBall(To);
}

void FFurySim::Knock(int32 Victim, int32 By, EFuryFall Fall, float DownSeconds, const FVector2D& Push, float Lift)
{
	FFurySimPlayer& V = Players[Victim];
	Disengage(Victim);
	const float Length = ActDuration(Fall);
	SetAct(V, EFuryAct::Hit, static_cast<uint8>(Fall), Length, 0.f, true);
	V.bDown = true;
	V.DownLeft = Length + DownSeconds;
	V.Launch = Push;
	V.Height = 0.f;
	V.EvadeLeft = V.StiffLeft = V.JumpLeft = 0.f;
	V.FaceYaw = V.Yaw;
	if (By != INDEX_NONE)
	{
		// Fall facing the way the hit dictates: knocked backward means facing the hitter.
		const FVector2D Toward = Players[By].P - V.P;
		if (!Toward.IsNearlyZero())
		{
			const float HitYaw = AngleOf(Toward);
			V.FaceYaw = Fall == EFuryFall::Front ? HitYaw + UE_PI : HitYaw;
		}
	}
}

void FFurySim::Engage(int32 Blocker, int32 Defender, float ShedSeconds)
{
	FFurySimPlayer& B = Players[Blocker];
	FFurySimPlayer& D = Players[Defender];
	if (!B.Free() || !D.Free() || B.bHasBall || D.bHasBall)
	{
		return;
	}
	B.Engaged = Defender; D.Engaged = Blocker;
	B.bBlocker = true; D.bBlocker = false;
	B.EngageTime = D.EngageTime = 0.f;
	B.ShedAt = D.ShedAt = ShedSeconds;
	SetAct(B, EFuryAct::Block, 0, 0.f, 0.f, false);
	SetAct(D, EFuryAct::Block, 0, 0.f, 0.f, false);
}

void FFurySim::Disengage(int32 Index)
{
	FFurySimPlayer& P = Players[Index];
	if (P.Engaged == INDEX_NONE)
	{
		return;
	}
	FFurySimPlayer& Other = Players[P.Engaged];
	Other.Engaged = INDEX_NONE;
	if (Other.Act == EFuryAct::Block)
	{
		SetAct(Other, EFuryAct::Move, 0, 0.f, 0.f, false);
	}
	P.Engaged = INDEX_NONE;
	if (P.Act == EFuryAct::Block)
	{
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
	}
}

// ---------------------------------------------------------------------------------------------
// Passing and kicking
// ---------------------------------------------------------------------------------------------

void FFurySim::StartThrow(int32 Passer, int32 Target)
{
	FFurySimPlayer& Q = Players[Passer];
	if (Q.bBusy || !Q.bHasBall || Target == INDEX_NONE || Target == Passer)
	{
		return;
	}
	SetAct(Q, EFuryAct::Throw, 0, 0.42f, 0.17f, true);
	Ball.Target = Target;
	Ball.Thrower = Passer;
	Q.Yaw = AngleOf(Players[Target].P - Q.P);
	Q.V *= 0.45f;
}

void FFurySim::ReleaseThrow(int32 Passer)
{
	FFurySimPlayer& Q = Players[Passer];
	if (!Q.bHasBall || Ball.Target == INDEX_NONE)
	{
		return;
	}
	const FFurySimPlayer& R = Players[Ball.Target];

	// Lead the receiver: find where he will be when the ball gets there.
	FVector2D Aim = R.P;
	float T = 0.5f;
	const bool bSettled = R.bRouteDone && R.V.SizeSquared() < 200.f * 200.f;
	for (int32 i = 0; i < 4; ++i)
	{
		const float Dist = FVector2D::Distance(Q.P, Aim);
		T = 0.26f + Dist / 2700.f;
		Aim = bSettled ? R.P : R.P + R.V * T;
	}
	Aim = ClampToField(Aim, 90.f);
	const float Dist = FVector2D::Distance(Q.P, Aim);

	// Accuracy: worse when long, hurried, or thrown on the run.
	float Spread = 0.034f - 0.006f * (TeamInfo(Q.Team).Passing - 3);
	const int32 Rusher = NearestOpponent(Passer, 2.6f * Yard);
	if (Rusher != INDEX_NONE) { Spread += 0.03f; }
	if (Q.V.SizeSquared() > 300.f * 300.f) { Spread += 0.02f; }
	if (Q.Seat == INDEX_NONE) { Spread *= 1.35f - 0.55f * CpuSkill; }
	if (Teams[Q.Team].InFury()) { Spread = 0.f; }
	const float Miss = FMath::Min(FMath::Abs(Random.FRandRange(-1.f, 1.f) + Random.FRandRange(-1.f, 1.f)), 1.7f) * Spread * Dist;
	Aim += FromAngle(RandRange(0.f, UE_TWO_PI)) * Miss;

	Q.bHasBall = false;
	Ball.State = EFuryBallState::Pass;
	Ball.Holder = INDEX_NONE;
	Ball.From = FVector(Q.P.X, Q.P.Y, 185.f);
	Ball.To = FVector(Aim.X, Aim.Y, 125.f);
	Ball.Time = 0.f;
	Ball.Duration = T;
	Ball.bTipped = false;
	Ball.bArrived = false;
	Ball.Pos = Ball.From;
	bPassThrown = true;
	PassSeat = Q.Seat;
	++Teams[Q.Team].Attempts;
	Emit(EFuryEvent::Throw, Q.Team, Passer, Ball.Target, Dist / Yard);

	// Defenders notice after a beat; nobody gets a second swipe at a ball they already missed.
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		P.CatchCool = 0.f;
		if (P.Team != Q.Team)
		{
			P.bBroke = false;
			P.Think = P.Seat != INDEX_NONE ? 0.f : RandRange(0.14f, 0.3f) * (1.4f - 0.9f * CpuSkill) - (TeamInfo(P.Team).Defense - 3) * 0.02f;
		}
	}

	// A human who throws to a computer team-mate takes over the receiver.
	if (Q.Seat != INDEX_NONE && Players[Ball.Target].Seat == INDEX_NONE)
	{
		SwitchSeat(Q.Seat, Ball.Target);
	}
}

void FFurySim::StartKick(int32 Kicker)
{
	FFurySimPlayer& K = Players[Kicker];
	const bool bPunt = PlayType == EFuryPlayType::Punt;
	SetAct(K, bPunt ? EFuryAct::Punt : EFuryAct::Kick, 0, bPunt ? 0.85f : 0.95f, bPunt ? 0.5f : 0.6f, true);
	K.Launch = FVector2D::ZeroVector;
	if (!bPunt)
	{
		// Run up so the plant foot lands beside the ball at the moment of contact.
		FVector2D Spot(Ball.Pos.X, Ball.Pos.Y);
		if (PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint)
		{
			const FFurySimPlayer& Holder = Players[Global(Offense, 6)];
			Spot = Holder.P + FVector2D(0.f, -OffenseDir() * 55.f);
		}
		const FVector2D To = Spot - K.P;
		const float Dist = To.Size();
		if (Dist > 60.f)
		{
			K.Launch = To / Dist * ((Dist - 45.f) / K.ActKey);
			K.Yaw = AngleOf(To);
		}
	}
}

void FFurySim::StrikeKick(int32 Kicker)
{
	FFurySimPlayer& K = Players[Kicker];
	K.Launch = FVector2D::ZeroVector;
	const int32 Receiving = 1 - K.Team;
	Ball.Holder = INDEX_NONE;
	Ball.Thrower = Kicker;
	Ball.Time = 0.f;
	Ball.bTipped = false;
	for (FFurySimPlayer& P : Players)
	{
		P.bHasBall = false;
		P.CatchCool = 0.f;
	}

	if (PlayType == EFuryPlayType::Kickoff)
	{
		const float Depth = RandRange(1.f, 8.f);
		const float Lateral = FMath::Clamp(KickSteer.Y * 16.f + RandRange(-7.f, 7.f), -20.f, 20.f);
		Ball.State = EFuryBallState::Kick;
		Ball.From = FVector(Ball.Pos.X, Ball.Pos.Y, 20.f);
		Ball.To = FVector(WorldX(Receiving, Depth), Lateral * Yard, 110.f);
		Ball.Duration = RandRange(3.3f, 3.8f);
		Emit(EFuryEvent::Kickoff, K.Team, Kicker);
	}
	else if (PlayType == EFuryPlayType::Punt)
	{
		const float D = OffenseDir();
		const float Net = RandRange(40.f, 52.f);
		const float LandX = D * FMath::Min(LosX * D + Net * Yard, GoalX + 2.5f * Yard);
		const float Lateral = FMath::Clamp(BallY / Yard * 0.5f + KickSteer.Y * 14.f + RandRange(-6.f, 6.f), -21.f, 21.f);
		Ball.State = EFuryBallState::Kick;
		Ball.From = FVector(K.P.X + D * 60.f, K.P.Y, 70.f);
		Ball.To = FVector(LandX, Lateral * Yard, 110.f);
		Ball.Duration = RandRange(3.3f, 3.8f);
		BallTeam = K.Team;
		Emit(EFuryEvent::PuntKick, K.Team, Kicker);
	}
	else
	{
		// Field goal or extra point: the meter decides how far off line the ball flies.
		const float D = OffenseDir();
		const float GoalPlane = D * EndLineX;
		const float KickYards = FieldGoalYards();
		if (!bKickLocked)
		{
			if (K.Seat == INDEX_NONE)
			{
				const float Sigma = FMath::Max(0.05f, 0.1f + 0.0045f * KickYards - 0.05f * CpuSkill);
				KickAim = FMath::Clamp((Rand() + Rand() + Rand() - 1.5f) * 2.f * Sigma, -1.f, 1.f);
			}
			else
			{
				KickAim = KickMeter;
			}
			bKickLocked = true;
		}
		bKickMeterLive = false;
		const float Offset = KickAim * KickSpread(KickYards) + RandRange(-KickScatter, KickScatter);
		const bool bShort = KickYards > MaxKickYards;
		Ball.bKickGood = !bShort && FMath::Abs(Offset) < CleanKickWidth;
		Ball.State = EFuryBallState::FieldGoal;
		Ball.From = FVector(Ball.Pos.X, Ball.Pos.Y, 15.f);
		Ball.To = FVector(GoalPlane + D * (bShort ? -500.f : 350.f), Offset, bShort ? 60.f : RandRange(650.f, 900.f));
		Ball.Duration = 1.05f + KickYards * 0.027f;
		Ball.Target = INDEX_NONE;
		Emit(EFuryEvent::FieldGoalKick, K.Team, Kicker, INDEX_NONE, KickYards);
	}
	Ball.Pos = Ball.From;
	bKickPossessed = false;
	bReturnEnteredField = false;
	bKickTouched = false;
}

// ---------------------------------------------------------------------------------------------
// Tackles and fumbles
// ---------------------------------------------------------------------------------------------

void FFurySim::Fumble(int32 Carrier, const FVector2D& Push)
{
	FFurySimPlayer& C = Players[Carrier];
	C.bHasBall = false;
	Ball.State = EFuryBallState::Loose;
	Ball.Holder = INDEX_NONE;
	Ball.Thrower = INDEX_NONE;
	Ball.Pos = FVector(C.P.X, C.P.Y, 95.f);
	const FVector2D Kick = Push * 0.55f + FromAngle(RandRange(0.f, UE_TWO_PI)) * RandRange(120.f, 320.f);
	Ball.Vel = FVector(Kick.X, Kick.Y, RandRange(260.f, 430.f));
	Ball.Time = 0.f;
	Emit(EFuryEvent::Fumble, C.Team, Carrier);
}

/** The ball carrier has been brought down (or stepped out) at SpotX: sort out what that means. */
void FFurySim::FinishCarrierDown(int32 Carrier, float SpotX, float SpotY, bool bOutOfBounds, int32 Tackler)
{
	const FFurySimPlayer& C = Players[Carrier];
	const float D = OffenseDir();
	const bool bScrimmage = PlayType == EFuryPlayType::Scrimmage;
	const bool bOwnPlay = C.Team == Offense && !bChangeOfPossession;
	const float Gain = (SpotX - StartLosX) * D / Yard;
	PlayYards = Gain;

	if (PlayType == EFuryPlayType::TwoPoint)
	{
		Emit(EFuryEvent::TwoPointNoGood, 1 - ScoringTeam);
		DownBall(SpotX, SpotY, TEXT("NO GOOD"), TEXT("TWO-POINT TRY FAILS"), 1 - ScoringTeam);
		return;
	}

	// A returner who has already brought the ball into the field can concede a safety.
	if (SpotX * Dir(C.Team) <= -GoalX)
	{
		if ((bScrimmage && bOwnPlay) || bReturnEnteredField)
		{
			const int32 Def = 1 - C.Team;
			Score(Def, 2, Tackler);
			PendingScoreTeam = Def;
			AddFury(Def, 0.4f);
			Emit(EFuryEvent::Safety, Def, Tackler);
			DownBall(SpotX, SpotY, TEXT("SAFETY"), TEXT("TWO POINTS"), Def);
		}
		else
		{
			Emit(EFuryEvent::Touchback, C.Team);
			DownBall(SpotX, SpotY, TEXT("TOUCHBACK"), TEXT(""), C.Team);
		}
		return;
	}

	if (bScrimmage && bOwnPlay)
	{
		FFuryTeamState& Stats = Teams[Offense];
		const bool bSack = C.Slot == 0 && !bPassThrown && !bBallCrossedLine && Gain < 0.f && CurrentOff.Kind == EFuryPlayKind::Pass;
		if (bPassThrown) { Stats.PassYards += FMath::RoundToInt32(Gain); }
		else if (!bSack) { Stats.RushYards += FMath::RoundToInt32(Gain); }
		bFirstDownMade = (SpotX - FirstDownX) * D >= 0.f;

		const int32 Whole = FMath::RoundToInt32(FMath::Abs(Gain));
		const FString Yards = Gain >= 0.5f ? FString::Printf(TEXT("+%d YARD%s"), Whole, Whole == 1 ? TEXT("") : TEXT("S"))
			: Gain <= -0.5f ? FString::Printf(TEXT("LOSS OF %d"), Whole) : FString(TEXT("NO GAIN"));
		if (bSack)
		{
			++Teams[Defense()].Sacks;
			if (Tackler != INDEX_NONE && Players[Tackler].Seat != INDEX_NONE) { ++Seats[Players[Tackler].Seat].Sacks; }
			AddFury(Defense(), 0.22f);
			Emit(EFuryEvent::Sack, Defense(), Tackler, Carrier);
			DownBall(SpotX, SpotY, TEXT("SACKED!"), Yards, Defense());
		}
		else if (bFirstDownMade)
		{
			if (Gain >= 20.f) { AddFury(Offense, 0.08f); }
			DownBall(SpotX, SpotY, TEXT("FIRST DOWN!"), Yards, Offense);
		}
		else
		{
			if (Gain < -0.5f) { AddFury(Defense(), 0.08f); }
			DownBall(SpotX, SpotY, bOutOfBounds ? TEXT("OUT OF BOUNDS") : TEXT(""), Yards, Offense);
		}
		return;
	}

	// A return: kick, punt, interception or fumble.
	const TCHAR* Title = PlayType == EFuryPlayType::Kickoff ? TEXT("KICK RETURN") : PlayType == EFuryPlayType::Punt ? TEXT("PUNT RETURN") : TEXT("TURNOVER");
	PlayYards = (SpotX - ReturnStartX) * Dir(C.Team) / Yard;
	DownBall(SpotX, SpotY, Title, FString::Printf(TEXT("%d YD RETURN   /   %s BALL"), FMath::RoundToInt32(PlayYards), *TeamInfo(C.Team).Abbr), C.Team);
}

bool FFurySim::Tackle(int32 TacklerIndex, int32 CarrierIndex, float Strength, bool bDive)
{
	FFurySimPlayer& T = Players[TacklerIndex];
	FFurySimPlayer& C = Players[CarrierIndex];
	if (Phase != EFuryPhase::Live || !C.bHasBall)
	{
		return false;
	}
	const bool bFuryHit = Teams[T.Team].InFury();
	const FVector2D ToTackler = (T.P - C.P).GetSafeNormal();
	const float Front = FVector2D::DotProduct(ToTackler, FromAngle(C.Yaw));     // 1 = tackler straight ahead

	// Evasion: a spin or a hurdle makes most tackles whiff.
	if (C.EvadeLeft > 0.f && !bFuryHit)
	{
		const bool bHurdling = C.Act == EFuryAct::Hurdle;
		const float Escape = bHurdling ? (bDive ? 0.95f : 0.25f) : 0.72f;
		if (Chance(Escape))
		{
			// A move beats one tackler, not the whole pursuit.
			if (!bHurdling) { C.EvadeLeft = 0.f; }
			T.Cooldown = 0.8f;
			if (!T.bBusy) { SetAct(T, EFuryAct::Stumble, 0, 0.5f, 0.f, true); T.Launch = T.V * 0.6f; }
			AddFury(C.Team, 0.02f);
			Emit(EFuryEvent::BrokenTackle, C.Team, CarrierIndex, TacklerIndex);
			return false;
		}
	}
	// A stiff arm flattens a tackler coming from the front or the side.
	if (C.StiffLeft > 0.f && Front > -0.25f && !bFuryHit && Chance(bDive ? 0.4f : 0.78f))
	{
		C.StiffLeft = 0.f;
		Knock(TacklerIndex, CarrierIndex, EFuryFall::Back, 1.1f, ToTackler * 420.f, 0.f);
		T.Cooldown = 1.f;
		AddFury(C.Team, 0.03f);
		Emit(EFuryEvent::StiffArm, C.Team, CarrierIndex, TacklerIndex);
		return false;
	}

	// A quarterback caught holding the ball goes down easily. One running a designed keeper is a runner.
	const bool bPocketQB = C.Slot == 0 && C.Team == Offense && !bBallCrossedLine && !bChangeOfPossession && C.Job.Job != EFuryJob::Keeper;
	float Odds = 0.74f + 0.2f * Strength + 0.22f * (T.Power - C.Power);
	if (bDive) { Odds += 0.14f; }
	if (PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt) { Odds += 0.08f; }    // coverage teams tackle surely
	if (Front < -0.3f) { Odds += 0.06f; }
	if (bPocketQB) { Odds += 0.2f; }
	if (T.Seat != INDEX_NONE) { Odds += 0.05f; }
	else { Odds += 0.25f * (CpuSkill - 0.5f); }       // better computer teams wrap up; weaker ones miss
	if (Teams[C.Team].InFury()) { Odds -= 0.25f; }
	Odds = bFuryHit ? 1.f : FMath::Clamp(Odds, 0.35f, 0.99f);

	if (!Chance(Odds))
	{
		// Broken tackle: the defender bounces off, the runner loses a step.
		T.Cooldown = 0.9f;
		if (!T.bBusy)
		{
			if (Chance(0.5f)) { Knock(TacklerIndex, CarrierIndex, EFuryFall::Back, 0.5f, ToTackler * 260.f, 0.f); }
			else { SetAct(T, EFuryAct::Stumble, 0, 0.5f, 0.f, true); T.Launch = T.V * 0.5f; }
		}
		C.V *= 0.72f;
		AddFury(C.Team, 0.02f);
		Emit(EFuryEvent::BrokenTackle, C.Team, CarrierIndex, TacklerIndex);
		return false;
	}

	// He is going down. How hard? A big hit is a deliberate one: the hit button, a defender
	// unloading, or a team in Fury.
	const bool bBig = bFuryHit || Strength >= 0.99f;
	EFuryFall Fall = Front > 0.35f ? EFuryFall::Back : Front < -0.35f ? EFuryFall::Front : (bBig ? EFuryFall::Spin : EFuryFall::Back);
	if (bBig && Chance(0.45f)) { Fall = EFuryFall::Flip; }
	const FVector2D Push = (-ToTackler) * (bBig ? 520.f : 300.f) + T.V * 0.35f;

	float FumbleOdds = 0.006f + 0.012f * Strength + (bBig ? 0.035f : 0.f);
	if (bFuryHit) { FumbleOdds *= 2.5f; }
	if (bPocketQB) { FumbleOdds *= 1.6f; }
	if (C.Act == EFuryAct::Hurdle) { FumbleOdds *= 2.f; }
	if (Teams[C.Team].InFury()) { FumbleOdds *= 0.3f; }
	if (PlayType == EFuryPlayType::TwoPoint) { FumbleOdds = 0.f; }
	const bool bFumble = Chance(FMath::Min(FumbleOdds, 0.45f));

	const float SpotX = C.P.X, SpotY = C.P.Y;
	Knock(CarrierIndex, TacklerIndex, Fall, bFumble ? 1.2f : 1.45f, Push, 0.f);
	T.Yaw = AngleOf(-ToTackler);
	if (bDive)
	{
		T.Launch = Push * 0.65f;
	}
	else if (T.Act != EFuryAct::BigHit && T.Act != EFuryAct::Shove)
	{
		// A running collision has already reached the opponent. Begin the wrap or
		// shoulder on its authored contact frame while the runner starts reacting.
		const float Key = bBig ? 0.12f : 0.18f;
		SetAct(T, bBig ? EFuryAct::BigHit : EFuryAct::Tackle, 0, bBig ? 0.48f : 0.63f, Key, true);
		T.ActTime = Key;
		T.bKeyDone = true;
		T.Launch = Push * (bBig ? 0.45f : 0.8f);
	}
	else
	{
		T.Launch = Push * 0.45f;
	}

	if (T.Seat != INDEX_NONE)
	{
		++Seats[T.Seat].Tackles;
		if (bBig) { ++Seats[T.Seat].BigHits; }
	}
	if (bBig) { ++Teams[T.Team].BigHits; }
	Emit(bBig ? EFuryEvent::BigHit : EFuryEvent::Tackle, T.Team, TacklerIndex, CarrierIndex, Strength);
	if (bBig) { AddFury(T.Team, 0.04f); }

	if (bFumble)
	{
		Fumble(CarrierIndex, Push);
		return true;
	}
	FinishCarrierDown(CarrierIndex, SpotX, SpotY, false, TacklerIndex);
	return true;
}

// ---------------------------------------------------------------------------------------------
// Catching
// ---------------------------------------------------------------------------------------------

void FFurySim::FieldKick(int32 Index)
{
	// A kickoff or punt coming down into somebody's arms.
	FFurySimPlayer& P = Players[Index];
	const bool bReceiving = Ball.Thrower == INDEX_NONE || P.Team != Players[Ball.Thrower].Team;
	const float Odds = P.Job.Job == EFuryJob::Returner ? 0.97f : bReceiving ? 0.82f : 0.5f;
	bKickTouched = true;
	if (Chance(Odds))
	{
		SetAct(P, EFuryAct::Catch, 0, 0.35f, 0.1f, false);
		GiveBall(Index);
		Emit(EFuryEvent::Catch, P.Team, Index);
	}
	else
	{
		// Muffed: live ball.
		Ball.State = EFuryBallState::Loose;
		Ball.Vel = FVector(RandRange(-260.f, 260.f), RandRange(-260.f, 260.f), RandRange(150.f, 320.f));
		Ball.Time = 0.f;
		Emit(EFuryEvent::Drop, P.Team, Index);
	}
}

void FFurySim::CompleteCatch(int32 Index)
{
	FFurySimPlayer& P = Players[Index];
	const bool bHigh = Ball.Pos.Z > 185.f;
	SetAct(P, EFuryAct::Catch, bHigh ? 1 : 0, bHigh ? 0.5f : 0.4f, 0.12f, false);
	if (Ball.Thrower != INDEX_NONE && P.Team == Players[Ball.Thrower].Team)
	{
		const float GainYards = (P.P.X - StartLosX) * OffenseDir() / Yard;
		++Teams[P.Team].Completions;
		GiveBall(Index);
		Emit(EFuryEvent::Catch, P.Team, Index, Ball.Thrower, GainYards);
		if (GainYards >= 20.f) { AddFury(P.Team, 0.08f); }
		return;
	}
	// Picked off.
	++Teams[P.Team].Picks;
	if (P.Seat != INDEX_NONE) { ++Seats[P.Seat].Picks; }
	GiveBall(Index);
	bChangeOfPossession = true;
	AddFury(P.Team, 0.35f);
	Emit(EFuryEvent::Intercept, P.Team, Index, Ball.Thrower);
	if (PlayType == EFuryPlayType::TwoPoint)
	{
		Emit(EFuryEvent::TwoPointNoGood, P.Team);
		DownBall(P.P.X, P.P.Y, TEXT("NO GOOD"), TEXT("PICKED OFF"), P.Team);
	}
}

/**
 * The pass has arrived within reach of one or more players: one contest decides it.
 * An open receiver nearly always catches it. With a defender in the picture it becomes a fight
 * decided by who is closer to the ball; a defender alone on the ball has jumped the route.
 */
void FFurySim::ResolveCatch(const TArray<int32, TInlineAllocator<Fury::NumPlayers>>& InReach)
{
	const FVector2D Flat(Ball.Pos.X, Ball.Pos.Y);
	const int32 PassTeam = Ball.Thrower != INDEX_NONE ? Players[Ball.Thrower].Team : Offense;
	int32 Receiver = INDEX_NONE, Defender = INDEX_NONE;
	float ReceiverDist = 1.e9f, DefenderDist = 1.e9f;
	for (const int32 i : InReach)
	{
		FFurySimPlayer& P = Players[i];
		P.CatchCool = 0.6f;
		const float Dist = FVector2D::Distance(P.P, Flat);
		if (P.Team == PassTeam)
		{
			// The intended man gets the nod over a team-mate who happens to be nearby.
			const float Rank = Dist - (i == Ball.Target ? 200.f : 0.f);
			if (Rank < ReceiverDist) { ReceiverDist = Rank; Receiver = i; }
		}
		else if (Dist < DefenderDist)
		{
			DefenderDist = Dist;
			Defender = i;
		}
	}
	if (Receiver != INDEX_NONE)
	{
		ReceiverDist = FVector2D::Distance(Players[Receiver].P, Flat);
	}

	float CatchOdds = 0.f, PickOdds = 0.f, TipOdds = 0.f;
	if (Receiver != INDEX_NONE)
	{
		const FFurySimPlayer& R = Players[Receiver];
		CatchOdds = R.Hands;
		if (Receiver != Ball.Target) { CatchOdds *= 0.85f; }
		if (Ball.bTipped) { CatchOdds *= 0.65f; }
		if (Defender != INDEX_NONE)
		{
			const float Edge = FMath::Clamp((DefenderDist - ReceiverDist) / 70.f, -1.f, 1.f);    // +1: receiver has the ball to himself
			CatchOdds *= 0.44f + 0.3f * Edge;
			if (Players[Defender].Seat == INDEX_NONE) { CatchOdds *= 1.08f - 0.16f * CpuSkill; }
			PickOdds = 0.045f - 0.04f * Edge;
			TipOdds = 0.22f - 0.1f * Edge;
		}
		if (R.JumpLeft > 0.f) { CatchOdds += 0.08f; }
		if (Teams[R.Team].InFury()) { CatchOdds += 0.15f; }
	}
	else if (Defender != INDEX_NONE)
	{
		// Nobody on offense is near it. At the catch point that is a jumped route (or a bad throw);
		// on the way there, a ball batted at the line.
		const bool bAtCatchPoint = Ball.Time > Ball.Duration * 0.6f;
		PickOdds = bAtCatchPoint ? 0.24f : 0.05f;
		TipOdds = bAtCatchPoint ? 0.45f : 0.3f;
	}
	if (Defender != INDEX_NONE)
	{
		const FFurySimPlayer& Df = Players[Defender];
		const bool bHumanTimed = Df.Seat != INDEX_NONE && Df.JumpLeft > 0.f;
		PickOdds += (TeamInfo(Df.Team).Defense - 3) * 0.008f + (Df.Hands - 0.75f) * 0.1f;
		if (Df.Seat == INDEX_NONE) { PickOdds *= 0.6f + 0.8f * CpuSkill; }
		if (bHumanTimed) { PickOdds += 0.18f; TipOdds += 0.3f; }
		if (Ball.bTipped) { PickOdds += 0.1f; }
		if (Teams[Df.Team].InFury()) { PickOdds += 0.12f; CatchOdds -= 0.15f; }
		PickOdds = FMath::Clamp(PickOdds, 0.f, 0.6f);
	}
	CatchOdds = FMath::Clamp(CatchOdds, 0.f, 0.99f);

	const float Roll = Rand();
	const bool bHigh = Ball.Pos.Z > 185.f;
	// Tally: 0 open catches tried, 1 contests, 2 defender-alone at the catch point, 3 defender-alone in the lane,
	// 4..6 picks from each of those, 7 tipped-ball contests.
	const int32 Kind = Receiver != INDEX_NONE ? (Defender != INDEX_NONE ? 1 : 0) : (Ball.Time > Ball.Duration * 0.6f ? 2 : 3);
	++Tally[Kind];
	if (Ball.bTipped) { ++Tally[7]; }
	if (Roll < CatchOdds)
	{
		CompleteCatch(Receiver);
	}
	else if (Roll < CatchOdds + PickOdds)
	{
		++Tally[3 + Kind];
		CompleteCatch(Defender);
	}
	else if (Defender != INDEX_NONE && Roll < CatchOdds + PickOdds + TipOdds)
	{
		// Batted. Usually it is knocked down; sometimes it pops up for anyone.
		Ball.bArrived = true;
		SetAct(Players[Defender], EFuryAct::Swat, 0, 0.5f, 0.1f, false);
		if (Receiver != INDEX_NONE) { SetAct(Players[Receiver], EFuryAct::Catch, bHigh ? 1 : 0, 0.4f, 0.12f, false); }
		const bool bPop = Chance(0.3f);
		Ball.bTipped = true;
		Ball.Vel = FVector(Ball.Vel.X * 0.2f + RandRange(-200.f, 200.f), Ball.Vel.Y * 0.2f + RandRange(-200.f, 200.f), bPop ? RandRange(300.f, 460.f) : RandRange(-120.f, 80.f));
		Ball.Time = Ball.Duration + 1.f;      // from here it is a free ballistic ball
		for (const int32 i : InReach) { Players[i].CatchCool = bPop ? 0.3f : 2.f; }
		Emit(EFuryEvent::Tip, Players[Defender].Team, Defender);
	}
	else if (Receiver != INDEX_NONE)
	{
		// Off his hands and down.
		Ball.bArrived = true;
		SetAct(Players[Receiver], EFuryAct::Catch, bHigh ? 1 : 0, 0.4f, 0.12f, false);
		Ball.bTipped = true;
		Ball.Vel = FVector(Ball.Vel.X * 0.25f + RandRange(-120.f, 120.f), Ball.Vel.Y * 0.25f + RandRange(-120.f, 120.f), RandRange(-60.f, 160.f));
		Ball.Time = Ball.Duration + 1.f;
		for (const int32 i : InReach) { Players[i].CatchCool = 2.f; }
		Emit(EFuryEvent::Drop, Players[Receiver].Team, Receiver);
	}
	// Otherwise the defender simply missed it and the ball flies on.
}

// ---------------------------------------------------------------------------------------------
// Action timing
// ---------------------------------------------------------------------------------------------

void FFurySim::StartStrike(int32 Index, EFuryAct Act, FVector2D Aim)
{
	FFurySimPlayer& P = Players[Index];
	const bool bBig = Act == EFuryAct::BigHit;
	const float Key = 0.12f;
	const float Reach = bBig ? 82.f : 102.f;
	const float Speed = bBig ? 900.f : 560.f;
	float Nearest = Reach + Speed * Key;
	FVector2D Heading = Aim.GetSafeNormal();
	float Lunge = Speed;
	for (const FFurySimPlayer& Other : Players)
	{
		if (Other.Team == P.Team || Other.bDown) { continue; }
		const FVector2D To = Other.P - P.P;
		const float Dist = To.Size();
		if (Dist >= Nearest || FVector2D::DotProduct(To, Aim) < Dist * 0.72f) { continue; }
		const FVector2D Lead = To + (Other.V * Key).GetClampedToMaxSize(35.f);
		const FVector2D Direction = Lead.GetSafeNormal();
		if (FVector2D::DotProduct(Direction, Aim) < 0.68f) { continue; }
		Nearest = Dist;
		Heading = Direction;
		Lunge = FMath::Clamp((float(Lead.Size()) - Reach) / Key, 0.f, Speed);
	}
	SetAct(P, Act, 0, bBig ? 0.48f : 0.42f, Key, true);
	P.Yaw = AngleOf(Heading);
	P.Launch = Heading * Lunge;
	P.Cooldown = 0.8f;
}

void FFurySim::StartElbow(int32 Index, int32 Target)
{
	FFurySimPlayer& P = Players[Index];
	const FFurySimPlayer& V = Players[Target];
	const FVector2D Chest = FloorChest(V);
	P.Yaw = AngleOf(Chest - P.P);
	SetAct(P, EFuryAct::ElbowDrop, 0, 0.95f, 0.53f, true);
	P.Mark = Target;
	const FVector2D Aim = Chest + (V.Launch * 0.20f).GetClampedToMaxSize(45.f);
	P.Launch = ((Aim - ElbowOffset(P.Yaw) - P.P) / P.ActKey).GetClampedToMaxSize(400.f);
	P.Cooldown = 1.3f;
}

void FFurySim::ActKey(int32 Index)
{
	FFurySimPlayer& P = Players[Index];
	switch (P.Act)
	{
	case EFuryAct::Throw:
		if (Phase == EFuryPhase::Live) { ReleaseThrow(Index); }
		break;
	case EFuryAct::Kick:
	case EFuryAct::Punt:
		if (Phase == EFuryPhase::Live) { StrikeKick(Index); }
		break;
	case EFuryAct::BigHit:
	case EFuryAct::Shove:
	{
		if (Phase != EFuryPhase::Live && !AfterWhistle()) { break; }
		const bool bBig = P.Act == EFuryAct::BigHit;
		const FVector2D Facing = FromAngle(P.Yaw);
		const FVector2D Contact = P.P + Facing * (bBig ? 72.f : 91.f);
		int32 Victim = INDEX_NONE;
		float Best = TNumericLimits<float>::Max();
		for (int32 i = 0; i < NumPlayers; ++i)
		{
			const FFurySimPlayer& O = Players[i];
			if (O.Team == P.Team || O.bDown) { continue; }
			const float Error = FVector2D::DistSquared(Contact, O.P);
			if (Error < Best && Error <= FMath::Square(O.Radius * 0.72f))
			{
				Best = Error;
				Victim = i;
			}
		}
		if (Victim == INDEX_NONE)
		{
			break;
		}
		if (Players[Victim].bHasBall && Phase == EFuryPhase::Live)
		{
			Tackle(Index, Victim, bBig ? 1.f : 0.7f, false);
		}
		else
		{
			const FVector2D Push = (Players[Victim].P - P.P).GetSafeNormal() * (bBig ? 460.f : 330.f);
			const EFuryFall Fall = FVector2D::DotProduct(FromAngle(Players[Victim].Yaw), Facing) > 0.35f ? EFuryFall::Front : EFuryFall::Back;
			Knock(Victim, Index, Fall, bBig ? 1.1f : 0.85f, Push, 0.f);
			P.Launch = Push * 0.38f;
			Emit(Phase == EFuryPhase::Live ? (bBig ? EFuryEvent::BigHit : EFuryEvent::Shove) : EFuryEvent::LateHit, P.Team, Index, Victim, bBig ? 0.9f : 0.5f);
			if (Phase == EFuryPhase::Live && bBig) { AddFury(P.Team, 0.03f); }
		}
		break;
	}
	case EFuryAct::ElbowDrop:
		if (AfterWhistle() && P.Mark != INDEX_NONE)
		{
			FFurySimPlayer& V = Players[P.Mark];
			const FVector2D Chest = FloorChest(V);
			if (V.Team != P.Team && OnFloor(V) && FVector2D::DistSquared(P.P + ElbowOffset(P.Yaw), Chest) < FMath::Square(40.f))
			{
				const uint8 Side = V.Act == EFuryAct::Hit ? uint8(V.Variant == uint8(EFuryFall::Front) || V.Variant == uint8(EFuryFall::Spin)) : V.Variant;
				SetAct(V, EFuryAct::GroundRecoil, Side, 0.32f, 0.f, true);
				V.Launch = FromAngle(P.Yaw) * 85.f;
				Emit(EFuryEvent::LateHit, P.Team, Index, P.Mark, 1.f);
				Events.Last().Pos = FVector(Chest, 30.f);
			}
		}
		P.Launch *= 0.12f;
		break;
	default:
		break;
	}
}

void FFurySim::ActEnd(int32 Index)
{
	FFurySimPlayer& P = Players[Index];
	switch (P.Act)
	{
	case EFuryAct::GroundRecoil:
		SetAct(P, EFuryAct::Down, P.Variant, 0.f, 0.f, true);
		break;
	case EFuryAct::Hit:
	{
		const EFuryFall Fall = static_cast<EFuryFall>(P.Variant);
		SetAct(P, EFuryAct::Down, (Fall == EFuryFall::Front || Fall == EFuryFall::Spin) ? 1 : 0, 0.f, 0.f, true);
		break;
	}
	case EFuryAct::Dive:
	case EFuryAct::Tackle:
	case EFuryAct::ElbowDrop:
		P.bDown = true;
		P.DownLeft = P.Act == EFuryAct::Dive ? 0.55f : 0.4f;
		SetAct(P, EFuryAct::Down, 1, 0.f, 0.f, true);
		break;
	case EFuryAct::DiveBall:
		P.bDown = true;
		P.DownLeft = 1.4f;
		SetAct(P, EFuryAct::Down, 1, 0.f, 0.f, true);
		if (P.bHasBall && Phase == EFuryPhase::Live)
		{
			FinishCarrierDown(Index, P.P.X + Dir(P.Team) * 40.f, P.P.Y, false, INDEX_NONE);
		}
		break;
	case EFuryAct::GetUp:
		P.bDown = false;
		P.Launch = FVector2D::ZeroVector;
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
		break;
	case EFuryAct::Celebrate:
		SetAct(P, EFuryAct::Celebrate, 2, 0.f, 0.f, true);
		break;
	case EFuryAct::Hurdle:
		P.V = P.Launch;
		P.Launch = FVector2D::ZeroVector;
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
		break;
	default:
		P.Launch = FVector2D::ZeroVector;
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
		break;
	}
}

// ---------------------------------------------------------------------------------------------
// Human control
// ---------------------------------------------------------------------------------------------

void FFurySim::StepHuman(FFurySimPlayer& P, int32 Index, const FFurySeatInput& In, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	FFurySeat& Seat = Seats[P.Seat];
	const bool bLive = Phase == EFuryPhase::Live;
	FVector2D Stick = StickToWorld(In.Stick);
	const bool bSteering = Stick.SizeSquared() > 0.03f;
	Seat.Idle = bSteering ? 0.f : Seat.Idle + Dt;

	// Turbo: a meter that drains while held and refills when released. Fury makes it bottomless.
	bool bTurbo = false;
	if (In.bTurbo && bSteering && !Seat.bTurboSpent)
	{
		bTurbo = true;
		if (!Teams[P.Team].InFury())
		{
			Seat.Turbo -= Dt * 0.4f;
			if (Seat.Turbo <= 0.f) { Seat.Turbo = 0.f; Seat.bTurboSpent = true; }
		}
	}
	else
	{
		Seat.Turbo = FMath::Min(1.f, Seat.Turbo + Dt * 0.27f);
		if (Seat.Turbo > 0.3f) { Seat.bTurboSpent = false; }
	}
	OutWish = Stick;
	OutSpeed = MaxSpeed(P, bTurbo);

	if (!bLive)
	{
		// After the whistle: wander, shove, flop. Nothing counts.
		if (AfterWhistle() && P.Cooldown <= 0.f)
		{
			const FVector2D Aim = bSteering ? Stick.GetSafeNormal() : FromAngle(P.Yaw);
			if (In.B)
			{
				StartStrike(Index, In.bTurbo ? EFuryAct::BigHit : EFuryAct::Shove, Aim);
			}
			else if (In.X)
			{
				// Aim at the nearest opponent in the input direction. A player
				// behind the controller should never steal the intended dive.
				int32 Near = INDEX_NONE;
				float Best = 2.6f * Yard;
				for (int32 j = 0; j < NumPlayers; ++j)
				{
					const FFurySimPlayer& O = Players[j];
					if (O.Team == P.Team) { continue; }
					const FVector2D To = O.P - P.P;
					const float Dist = To.Size();
					if (Dist < Best && (!bSteering || FVector2D::DotProduct(To, Aim) >= 0.5f * Dist))
					{
						Best = Dist;
						Near = j;
					}
				}
				if (Near != INDEX_NONE && Players[Near].bDown && Players[Near].Act != EFuryAct::GetUp)
				{
					StartElbow(Index, Near);
				}
				else
				{
					SetAct(P, EFuryAct::Dive, 0, 0.55f, 0.f, true);
					const FVector2D Heading = Near != INDEX_NONE ? (Players[Near].P - P.P).GetSafeNormal() : Aim;
					P.Yaw = AngleOf(Heading);
					P.Launch = Heading * 1100.f;
					P.Cooldown = 1.1f;
					Emit(EFuryEvent::Dive, P.Team, Index);
				}
			}
		}
		else if (!AfterWhistle())
		{
			// Between plays the stick is busy with menus, so the computer walks everyone to the huddle.
			ThinkAfterWhistle(P, Index, Dt, OutWish, OutSpeed);
		}
		return;
	}

	const bool bScrimmage = PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint;
	const float D = Dir(P.Team);

	if (P.bHasBall)
	{
		const bool bCanPass = bScrimmage && P.Team == Offense && !bChangeOfPossession && !bPassThrown && (P.P.X - LosX) * OffenseDir() < 0.f;
		if (bCanPass && P.Slot == 0 && CurrentOff.Kind != EFuryPlayKind::Run)
		{
			// Quarterback: a button per receiver. Y = top of the screen, X or B = middle, A = bottom.
			const int32 Icon = In.Y ? 1 : (In.X || In.B) ? 2 : In.A ? 3 : 0;
			if (Icon != 0 && LiveTime > 0.1f)
			{
				for (int32 Slot = 0; Slot < TeamSize; ++Slot)
				{
					const int32 Target = Global(P.Team, Slot);
					if (Players[Target].PassIcon == Icon && !Players[Target].bDown)
					{
						StartThrow(Index, Target);
						break;
					}
				}
			}
			P.bFace = true;
			P.FaceYaw = OffenseDir() > 0.f ? 0.f : UE_PI;
			if (P.Free() && !bSteering && Seat.Idle > 0.05f && LiveTime < 1.2f)
			{
				// Hands off the stick: drop back automatically.
				const FVector2D Spot = P.Home - FVector2D(OffenseDir() * CurrentOff.Drop * Yard, 0.f);
				const FVector2D To = Spot - P.P;
				if (To.SizeSquared() > 30.f * 30.f)
				{
					OutWish = To.GetSafeNormal();
					OutSpeed = P.TopSpeed * 0.8f;
				}
			}
			else if (bSteering)
			{
				// Only keep facing downfield while backing up; turn and run when heading upfield.
				P.bFace = Stick.X * OffenseDir() < 0.3f;
			}
			return;
		}
		if (bCanPass && P.Slot == 0)
		{
			// A designed run with the quarterback still holding it: let the hand-off logic work.
			if (!bSteering)
			{
				ThinkPasser(P, Index, Dt, OutWish, OutSpeed);
				return;
			}
		}

		// Ball carrier moves.
		if (P.Cooldown <= 0.f)
		{
			if (In.A)
			{
				SetAct(P, EFuryAct::Spin, 0, 0.5f, 0.f, false);
				P.EvadeLeft = 0.38f;
				P.Cooldown = 1.6f;
				Emit(EFuryEvent::Spin, P.Team, Index);
			}
			else if (In.B)
			{
				SetAct(P, EFuryAct::StiffArm, 0, 0.45f, 0.15f, false);
				P.StiffLeft = 0.4f;
				P.Cooldown = 1.6f;
			}
			else if (In.Y)
			{
				SetAct(P, EFuryAct::Hurdle, 0, 0.6f, 0.f, true);
				P.EvadeLeft = 0.5f;
				P.Launch = (P.V.SizeSquared() > 100.f * 100.f ? P.V.GetSafeNormal() : FromAngle(P.Yaw)) * OutSpeed * 0.9f;
				P.Cooldown = 1.8f;
				Emit(EFuryEvent::Hurdle, P.Team, Index);
			}
			else if (In.X)
			{
				SetAct(P, EFuryAct::DiveBall, 0, 0.6f, 0.f, true);
				P.Launch = (bSteering ? Stick.GetSafeNormal() : FromAngle(P.Yaw)) * OutSpeed * 1.1f;
				P.Yaw = AngleOf(P.Launch);
				P.Cooldown = 2.f;
				Emit(EFuryEvent::Dive, P.Team, Index);
			}
		}
		if (P.Act == EFuryAct::Spin) { OutSpeed *= 0.85f; }
		return;
	}

	const bool bMyTeamHasBall = BallTeam == P.Team && Ball.State != EFuryBallState::Loose;
	const bool bBallInAir = Ball.State == EFuryBallState::Pass || Ball.State == EFuryBallState::Kick;

	if (bMyTeamHasBall && !(bBallInAir && Ball.State == EFuryBallState::Kick && Players[Ball.Thrower].Team == P.Team))
	{
		// Offense without the ball: run the route yourself, or leave the stick alone and it runs itself.
		if (In.A && bScrimmage && !bPassThrown)
		{
			// Call for the ball from a computer quarterback.
			const int32 QB = CarrierIndex();
			if (QB != INDEX_NONE && Players[QB].Team == P.Team && Players[QB].Seat == INDEX_NONE && Players[QB].Slot == 0 && (Players[QB].P.X - LosX) * OffenseDir() < 0.f)
			{
				StartThrow(QB, Index);
			}
		}
		if ((In.Y || In.X) && bBallInAir)
		{
			P.JumpLeft = 0.45f;
		}
		if (In.B && P.Cooldown <= 0.f)
		{
			StartStrike(Index, EFuryAct::Shove, bSteering ? Stick.GetSafeNormal() : FromAngle(P.Yaw));
		}
		if (P.Free() && !bSteering && Seat.Idle > 0.12f)
		{
			ThinkPlayer(P, Index, Dt, OutWish, OutSpeed);
		}
		return;
	}

	// Defense (or a scramble for a loose ball).
	if (In.A)
	{
		const int32 Next = ClosestToBall(P.Team, true, Index);
		if (Next != INDEX_NONE)
		{
			SwitchSeat(P.Seat, Next);
			return;
		}
	}
	if (P.Cooldown <= 0.f)
	{
		const float Heading = bSteering ? AngleOf(Stick) : P.Yaw;
		if (In.X)
		{
			SetAct(P, EFuryAct::Dive, 0, 0.55f, 0.f, true);
			P.Launch = FromAngle(Heading) * 1250.f;
			P.Yaw = Heading;
			P.Cooldown = 1.f;
			Emit(EFuryEvent::Dive, P.Team, Index);
		}
		else if (In.B)
		{
			StartStrike(Index, EFuryAct::BigHit, FromAngle(Heading));
		}
		else if (In.Y)
		{
			SetAct(P, EFuryAct::Swat, 0, 0.7f, 0.28f, true);
			P.JumpLeft = 0.55f;
			P.Launch = P.V * 0.5f;
			P.Cooldown = 0.9f;
		}
	}
	if (P.Free() && !bSteering && Seat.Idle > 0.6f)
	{
		// A human who has let go of the stick is covered by the computer until they take over again.
		ThinkPlayer(P, Index, Dt, OutWish, OutSpeed);
	}
}

// ---------------------------------------------------------------------------------------------
// Movement and contact
// ---------------------------------------------------------------------------------------------

void FFurySim::MovePlayers(float Dt, const FVector2D* Wish, const float* Speed)
{
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		if (P.Engaged != INDEX_NONE)
		{
			continue;
		}
		if (P.bDown || P.bBusy)
		{
			// Carried by momentum: a dive, a lunge, or flying from a hit.
			float Drag = 4.f;
			switch (P.Act)
			{
			case EFuryAct::Dive: Drag = P.ActTime < 0.28f ? 0.f : 6.f; break;
			case EFuryAct::DiveBall: Drag = P.ActTime < 0.3f ? 0.f : 6.f; break;
			case EFuryAct::BigHit: case EFuryAct::Shove: Drag = P.ActTime < 0.14f ? 0.f : 10.f; break;
			case EFuryAct::Hurdle: Drag = 0.f; break;
			case EFuryAct::Kick: Drag = P.bKeyDone ? 12.f : 0.f; break;
			case EFuryAct::Hit:
				Drag = 3.2f;
				P.Yaw += FMath::Clamp(AngleDelta(P.Yaw, P.FaceYaw), -Dt * 18.f, Dt * 18.f);
				break;
			case EFuryAct::Tackle: Drag = 5.f; break;
			case EFuryAct::ElbowDrop: Drag = !P.bKeyDone ? 0.f : 14.f; break;
			case EFuryAct::Down: case EFuryAct::GetUp: Drag = 9.f; break;
			default: Drag = 7.f; break;
			}
			const float Drive = P.Act == EFuryAct::Dive && P.ActTime < 0.055f ? 0.32f : 1.f;
			P.P += P.Launch * (Dt * Drive);
			P.Launch *= FMath::Exp(-Drag * Dt);
			P.V = P.Launch;
		}
		else
		{
			FVector2D Want = Wish[i];
			const float Size = Want.Size();
			if (Size > 1.f)
			{
				Want /= Size;
			}
			const FVector2D Target = Want * Speed[i];
			const FVector2D Delta = Target - P.V;
			const float Rate = (Target.SizeSquared() >= P.V.SizeSquared() ? Accel : Decel) * Dt;
			const float DeltaSize = Delta.Size();
			P.V = DeltaSize <= Rate ? Target : P.V + Delta / DeltaSize * Rate;
			P.P += P.V * Dt;

			float WantYaw = P.Yaw;
			if (P.bFace)
			{
				WantYaw = P.FaceYaw;
			}
			else if (P.V.SizeSquared() > 70.f * 70.f)
			{
				WantYaw = AngleOf(P.V);
			}
			const float Turn = AngleDelta(P.Yaw, WantYaw);
			P.Yaw += FMath::Clamp(Turn, -TurnRate * Dt, TurnRate * Dt);
		}
		// Athletes may leave the field of play but not the stadium floor.
		P.P.X = FMath::Clamp(P.P.X, -EndLineX - 250.f, EndLineX + 250.f);
		P.P.Y = FMath::Clamp(P.P.Y, -SidelineY - 280.f, SidelineY + 280.f);
	}
}

void FFurySim::Separate()
{
	for (int32 a = 0; a < NumPlayers; ++a)
	{
		FFurySimPlayer& A = Players[a];
		if (A.bDown)
		{
			continue;
		}
		for (int32 b = a + 1; b < NumPlayers; ++b)
		{
			FFurySimPlayer& B = Players[b];
			if (B.bDown || A.Engaged == b)
			{
				continue;
			}
			const FVector2D Delta = B.P - A.P;
			const float Dist = Delta.Size();
			const float Min = (A.Radius + B.Radius) * 0.9f;
			if (Dist >= Min || Dist < 0.01f)
			{
				continue;
			}
			const FVector2D Normal = Delta / Dist;
			const float Overlap = Min - Dist;
			const bool bAnchorA = A.Engaged != INDEX_NONE || A.bBusy;
			const bool bAnchorB = B.Engaged != INDEX_NONE || B.bBusy;
			const float ShareA = bAnchorA == bAnchorB ? 0.5f : bAnchorA ? 0.f : 1.f;
			A.P -= Normal * Overlap * ShareA;
			B.P += Normal * Overlap * (1.f - ShareA);
		}
	}
}

void FFurySim::StepEngagements(float Dt)
{
	const int32 Carrier = CarrierIndex();
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& B = Players[i];
		if (B.Engaged == INDEX_NONE || !B.bBlocker)
		{
			continue;
		}
		const int32 j = B.Engaged;
		FFurySimPlayer& Df = Players[j];
		if (Phase != EFuryPhase::Live || B.bDown || Df.bDown)
		{
			Disengage(i);
			continue;
		}

		// The defender fights toward the ball; humans fight faster by holding turbo.
		float Rate = 1.f;
		if (Df.Seat != INDEX_NONE && Seats[Df.Seat].Turbo > 0.05f) { Rate = 1.7f; }
		if (B.Seat != INDEX_NONE) { Rate *= 0.75f; }
		B.EngageTime += Dt * Rate;

		FVector2D Goal(Ball.Pos.X, Ball.Pos.Y);
		if (Carrier != INDEX_NONE)
		{
			Goal = Players[Carrier].P;
		}
		const FVector2D ToGoal = (Goal - Df.P).GetSafeNormal();
		float Push = 45.f + 150.f * (Df.Power - B.Power);
		if (Teams[Df.Team].InFury()) { Push += 90.f; }
		if (Teams[B.Team].InFury()) { Push -= 120.f; }
		if (B.Job.Job == EFuryJob::RunBlock || bBallCrossedLine) { Push -= 70.f; }
		Df.P += ToGoal * Push * Dt;
		B.P = Df.P + ToGoal * (Df.Radius + B.Radius) * 0.92f;
		Df.V = B.V = ToGoal * Push;
		Df.Yaw = AngleOf(ToGoal);
		B.Yaw = Df.Yaw + UE_PI;

		// Once the ball is well past them there is nothing left to fight over.
		bool bRelease = false;
		if (Carrier != INDEX_NONE && Players[Carrier].Team == B.Team)
		{
			const float Past = (Players[Carrier].P.X - Df.P.X) * Dir(B.Team);
			bRelease = Past > 3.5f * Yard && B.EngageTime > 0.5f;
		}
		if (B.EngageTime >= B.ShedAt || bRelease)
		{
			Disengage(i);
			if (Teams[B.Team].InFury() && Chance(0.5f))
			{
				Knock(j, i, EFuryFall::Back, 1.2f, ToGoal * -380.f, 0.f);
				Emit(EFuryEvent::Pancake, B.Team, i, j);
			}
			else
			{
				Df.Burst = 1.2f;
				Df.React = bRelease ? 0.25f : 0.f;
				SetAct(B, EFuryAct::Stumble, 0, 0.5f, 0.f, true);
				B.Launch = ToGoal * -160.f;
				B.Cooldown = 1.f;
			}
		}
	}
}

void FFurySim::StepContacts(float Dt)
{
	const int32 Carrier = CarrierIndex();

	// The arms reach out in front of the diver. Resolve one contest and play
	// the clamp on that step, even when a different defender ends the play.
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		if (P.Act != EFuryAct::Dive || P.bDiveSpent || P.bDown || P.ActTime < 0.055f || P.ActTime > 0.36f) { continue; }
		const FVector2D Facing = FromAngle(P.Yaw);
		const FVector2D Reach = P.P + Facing * 97.f;
		float Best = TNumericLimits<float>::Max();
		int32 Victim = INDEX_NONE;
		for (int32 j = 0; j < NumPlayers; ++j)
		{
			const FFurySimPlayer& O = Players[j];
			if (O.Team == P.Team || O.bDown) { continue; }
			const float Error = FVector2D::DistSquared(Reach, O.P);
			if (Error < Best && Error <= FMath::Square(O.Radius + 9.f)) { Victim = j; Best = Error; }
		}
		if (Victim == INDEX_NONE) { continue; }
		P.bDiveSpent = true;
		// The rig closes its arms eight frames into a 24-frame dive.
		P.ActKey = P.ActTime;
		P.ActLength = P.ActTime + 0.36f;
		P.Yaw = AngleOf(Players[Victim].P - P.P);
		if (Victim == Carrier && Phase == EFuryPhase::Live)
		{
			FFurySimPlayer& C = Players[Carrier];
			if (C.Act == EFuryAct::DiveBall)
			{
				Emit(EFuryEvent::Tackle, P.Team, i, Carrier, 0.3f);
				FinishCarrierDown(Carrier, C.P.X, C.P.Y, false, i);
			}
			else { Tackle(i, Victim, 0.78f, true); }
		}
		else
		{
			const FVector2D Drive = FromAngle(P.Yaw);
			const EFuryFall Fall = FVector2D::DotProduct(FromAngle(Players[Victim].Yaw), Drive) > 0.35f ? EFuryFall::Front : EFuryFall::Back;
			Knock(Victim, i, Fall, 1.f, Drive * 480.f, 0.f);
			P.Launch = Drive * 320.f;
			Emit(AfterWhistle() ? EFuryEvent::LateHit : EFuryEvent::Shove, P.Team, i, Victim, 0.8f);
		}
	}

	if (Phase != EFuryPhase::Live || Carrier == INDEX_NONE)
	{
		return;
	}
	const FFurySimPlayer& C = Players[Carrier];
	if (C.bDown && C.Act != EFuryAct::DiveBall)
	{
		return;
	}
	for (int32 i = 0; i < NumPlayers && Phase == EFuryPhase::Live; ++i)
	{
		FFurySimPlayer& T = Players[i];
		if (T.Team == C.Team || T.bDown || T.Engaged != INDEX_NONE || T.Cooldown > 0.f)
		{
			continue;
		}
		if (T.bBusy)
		{
			continue;
		}
		const float Reach = T.Radius + C.Radius + 8.f;
		if (FVector2D::DistSquared(T.P, C.P) > Reach * Reach)
		{
			continue;
		}
		if (C.Act == EFuryAct::DiveBall)
		{
			// He has already given himself up: touched down where he is.
			Emit(EFuryEvent::Tackle, T.Team, i, Carrier, 0.3f);
			FinishCarrierDown(Carrier, C.P.X, C.P.Y, false, i);
			break;
		}
		// Closing speed and muscle decide how hard the hit is.
		const float Closing = FVector2D::DotProduct(T.V - C.V, (C.P - T.P).GetSafeNormal());
		float Strength = FMath::Min(FMath::Clamp(Closing / 900.f, 0.f, 1.f) * 0.6f + T.Power * 0.4f, 0.95f);
		if (T.Seat == INDEX_NONE && Chance(0.1f + 0.2f * (T.Power - 0.5f)))
		{
			Strength = 1.f;      // a computer defender unloads
		}
		if (!Tackle(i, Carrier, Strength, false))
		{
			T.Cooldown = FMath::Max(T.Cooldown, 0.7f);
		}
		if (CarrierIndex() != Carrier)
		{
			break;
		}
	}
}

// ---------------------------------------------------------------------------------------------
// The ball
// ---------------------------------------------------------------------------------------------

void FFurySim::StepBall(float Dt)
{
	if (AfterWhistle()) { return; }
	const bool bLive = Phase == EFuryPhase::Live;
	Ball.Spin += Dt * 14.f;
	switch (Ball.State)
	{
	case EFuryBallState::Held:
		if (Ball.Holder != INDEX_NONE)
		{
			const FFurySimPlayer& H = Players[Ball.Holder];
			Ball.Pos = FVector(H.P.X, H.P.Y, H.bDown ? 25.f : 110.f);
		}
		break;

	case EFuryBallState::Snap:
	{
		Ball.Time += Dt;
		const float Alpha = FMath::Clamp(Ball.Time / FMath::Max(Ball.Duration, 0.01f), 0.f, 1.f);
		const FFurySimPlayer& Taker = Players[Ball.Target];
		const FVector End(Taker.P.X, Taker.P.Y, Ball.To.Z);
		Ball.Pos = FMath::Lerp(Ball.From, End, Alpha) + FVector(0.f, 0.f, FMath::Sin(Alpha * UE_PI) * 28.f);
		if (Alpha >= 1.f)
		{
			FFurySimPlayer& Catcher = Players[Ball.Target];
			if (Catcher.bDown)
			{
				Ball.State = EFuryBallState::Loose;
				Ball.Vel = FVector(RandRange(-200.f, 200.f), RandRange(-200.f, 200.f), 200.f);
				Ball.Time = 0.f;
				Emit(EFuryEvent::Fumble, Catcher.Team, Ball.Target);
			}
			else if (Catcher.Job.Job == EFuryJob::Holder)
			{
				// Spotted for the kicker.
				Ball.State = EFuryBallState::Tee;
				Ball.Pos = FVector(Catcher.P.X, Catcher.P.Y - OffenseDir() * 55.f, 14.f);
			}
			else
			{
				GiveBall(Ball.Target);
				if (Catcher.Job.Job == EFuryJob::Punter)
				{
					StartKick(Ball.Target);
				}
				else if (Catcher.Act != EFuryAct::Move || Catcher.Slot == 0)
				{
					SetAct(Catcher, EFuryAct::CatchSnap, 0, 0.3f, 0.12f, false);
				}
			}
		}
		break;
	}

	case EFuryBallState::Pass:
	case EFuryBallState::Kick:
	case EFuryBallState::FieldGoal:
	{
		Ball.Time += Dt;
		if (Ball.Time <= Ball.Duration)
		{
			const float T = Ball.Time;
			const float Total = FMath::Max(Ball.Duration, 0.05f);
			const float Vz0 = (Ball.To.Z - Ball.From.Z + 0.5f * Gravity * Total * Total) / Total;
			const FVector Flat = (Ball.To - Ball.From) / Total;
			Ball.Pos = FVector(Ball.From.X + Flat.X * T, Ball.From.Y + Flat.Y * T, Ball.From.Z + Vz0 * T - 0.5f * Gravity * T * T);
			Ball.Vel = FVector(Flat.X, Flat.Y, Vz0 - Gravity * T);
		}
		else
		{
			Ball.Vel.Z -= Gravity * Dt;
			Ball.Pos += Ball.Vel * Dt;
		}

		if (Ball.State == EFuryBallState::FieldGoal)
		{
			const float D = OffenseDir();
			if ((Ball.Pos.X - D * EndLineX) * D >= 0.f || Ball.Pos.Z <= BallRadius)
			{
				const bool bExtra = PlayType == EFuryPlayType::ExtraPoint;
				const int32 Kicker = Ball.Thrower;
				Ball.State = EFuryBallState::Dead;
				if (!bLive)
				{
					break;
				}
				if (Ball.bKickGood)
				{
					Score(Offense, bExtra ? 1 : 3, Kicker);
					Emit(bExtra ? EFuryEvent::ExtraPointGood : EFuryEvent::FieldGoalGood, Offense, Kicker);
					if (!bExtra) { PendingScoreTeam = Offense; }
					DownBall(Ball.Pos.X, 0.f, bExtra ? TEXT("EXTRA POINT") : TEXT("FIELD GOAL"), TEXT("IT'S GOOD!"), Offense);
				}
				else
				{
					if (FMath::Abs(FMath::Abs(Ball.Pos.Y) - UprightHalfWidth) < 45.f) { Emit(EFuryEvent::Doink, Offense); }
					Emit(bExtra ? EFuryEvent::ExtraPointNoGood : EFuryEvent::FieldGoalNoGood, Offense, Kicker);
					DownBall(StartLosX, BallY, TEXT("NO GOOD"), bExtra ? TEXT("EXTRA POINT MISSED") : TEXT("FIELD GOAL MISSED"), Defense());
				}
			}
			break;
		}

		// Out of the field of play in the air.
		if (bLive && (FMath::Abs(Ball.Pos.Y) > SidelineY + 40.f || FMath::Abs(Ball.Pos.X) > EndLineX + 40.f) && Ball.Pos.Z < 250.f)
		{
			if (Ball.State == EFuryBallState::Pass)
			{
				Emit(EFuryEvent::Incomplete, Offense);
				Ball.State = EFuryBallState::Dead;
				if (PlayType == EFuryPlayType::TwoPoint) { Emit(EFuryEvent::TwoPointNoGood, 1 - ScoringTeam); }
				DownBall(StartLosX, BallY, PlayType == EFuryPlayType::TwoPoint ? TEXT("NO GOOD") : TEXT("INCOMPLETE"), TEXT(""), Defense());
			}
			else
			{
				const int32 Receiving = 1 - Players[Ball.Thrower].Team;
				const bool bEndZone = Ball.Pos.X * Dir(Receiving) < -GoalX;
				Ball.State = EFuryBallState::Dead;
				BallTeam = Receiving;
				if (bEndZone) { Emit(EFuryEvent::Touchback, Receiving); DownBall(Ball.Pos.X, 0.f, TEXT("TOUCHBACK"), TEXT(""), Receiving); }
				else
				{
					const float SpotX = PlayType == EFuryPlayType::Kickoff ? WorldX(Receiving, 35.f) : Ball.Pos.X;
					DownBall(SpotX, 0.f, TEXT("OUT OF BOUNDS"), FString::Printf(TEXT("%s BALL"), *TeamInfo(Receiving).Name.ToUpper()), Receiving);
				}
			}
			break;
		}

		// Who gets a hand on it?
		if (bLive && Ball.State == EFuryBallState::Kick)
		{
			// A kick can be fielded as it comes down; the returner has first claim.
			if (Ball.Time > Ball.Duration - 0.45f)
			{
				const FVector2D Flat(Ball.Pos.X, Ball.Pos.Y);
				int32 Fielder = INDEX_NONE;
				float FielderDist = 1.e12f;
				for (int32 i = 0; i < NumPlayers; ++i)
				{
					FFurySimPlayer& P = Players[i];
					if (P.bDown || P.CatchCool > 0.f || i == Ball.Thrower || P.Engaged != INDEX_NONE || Ball.Pos.Z > 235.f)
					{
						continue;
					}
					const float Dist = FVector2D::DistSquared(P.P, Flat);
					if (Dist > CatchReach * CatchReach)
					{
						continue;
					}
					P.CatchCool = 0.6f;
					const float Rank = Dist - (P.Job.Job == EFuryJob::Returner ? 1.e9f : 0.f);
					if (Rank < FielderDist) { FielderDist = Rank; Fielder = i; }
				}
				if (Fielder != INDEX_NONE)
				{
					FieldKick(Fielder);
				}
			}
		}
		else if (bLive && Ball.State == EFuryBallState::Pass)
		{
			// Three moments matter for a pass:
			//  - on the way, a defender standing in the lane can bat it (rare: most throws clear him);
			//  - at the catch point, everyone close by contests it once, receiver and defenders together;
			//  - after that (a tip, an overthrow) it is a free ball for anyone who can reach it.
			const FVector2D Flat(Ball.Pos.X, Ball.Pos.Y);
			const int32 PassTeam = Ball.Thrower != INDEX_NONE ? Players[Ball.Thrower].Team : Offense;
			const bool bAtCatchPoint = !Ball.bArrived && Ball.Time >= Ball.Duration - Dt * 0.5f;
			const bool bInLane = !Ball.bArrived && !bAtCatchPoint && Ball.Time > 0.2f && Ball.Time < Ball.Duration - 0.15f;
			const bool bFree = Ball.bArrived;
			if (bAtCatchPoint || bInLane || bFree)
			{
				TArray<int32, TInlineAllocator<NumPlayers>> InReach;
				for (int32 i = 0; i < NumPlayers; ++i)
				{
					const FFurySimPlayer& P = Players[i];
					if (P.bDown || P.CatchCool > 0.f || i == Ball.Thrower || P.Engaged != INDEX_NONE)
					{
						continue;
					}
					const bool bMate = P.Team == PassTeam;
					if (bInLane && bMate)
					{
						continue;
					}
					const bool bJump = P.JumpLeft > 0.f;
					float Reach = CatchReach + (bJump ? 32.f : 0.f);
					if (bAtCatchPoint)
					{
						// The designed catch: the receiver finishes his stride to it, defenders lunge.
						Reach = (bMate ? 150.f : 122.f) + (bJump ? 32.f : 0.f);
					}
					const float Top = bJump ? 300.f : 222.f;
					if (Ball.Pos.Z > Top || Ball.Pos.Z < 18.f || FVector2D::DistSquared(P.P, Flat) > Reach * Reach)
					{
						continue;
					}
					InReach.Add(i);
				}
				if (bAtCatchPoint)
				{
					Ball.bArrived = true;
				}
				if (InReach.Num() > 0)
				{
					ResolveCatch(InReach);
				}
			}
		}

		// Hits the turf.
		if ((Ball.State == EFuryBallState::Pass || Ball.State == EFuryBallState::Kick) && Ball.Pos.Z <= BallRadius)
		{
			Ball.Pos.Z = BallRadius;
			if (Ball.State == EFuryBallState::Pass)
			{
				Ball.State = EFuryBallState::Dead;
				Ball.Vel = FVector(Ball.Vel.X * 0.4f, Ball.Vel.Y * 0.4f, 0.f);
				if (bLive)
				{
					Emit(EFuryEvent::Incomplete, Offense);
					if (PlayType == EFuryPlayType::TwoPoint) { Emit(EFuryEvent::TwoPointNoGood, 1 - ScoringTeam); }
					DownBall(StartLosX, BallY, PlayType == EFuryPlayType::TwoPoint ? TEXT("NO GOOD") : TEXT("INCOMPLETE"), TEXT(""), Defense());
				}
			}
			else
			{
				// A kick nobody fielded: it bounces around, live.
				Ball.State = EFuryBallState::Loose;
				Ball.Vel = FVector(Ball.Vel.X * 0.55f, Ball.Vel.Y * 0.55f + RandRange(-150.f, 150.f), FMath::Abs(Ball.Vel.Z) * 0.42f);
				Ball.Time = 0.f;
			}
		}
		break;
	}

	case EFuryBallState::Loose:
	{
		Ball.Time += Dt;
		Ball.Vel.Z -= Gravity * Dt;
		Ball.Pos += Ball.Vel * Dt;
		if (Ball.Pos.Z <= BallRadius)
		{
			Ball.Pos.Z = BallRadius;
			if (Ball.Vel.Z < -120.f)
			{
				// A football never bounces straight.
				const float Kick = RandRange(-0.5f, 0.5f);
				const FVector2D Flat = FVector2D(Ball.Vel.X, Ball.Vel.Y).GetRotated(FMath::RadiansToDegrees(Kick)) * 0.72f;
				Ball.Vel = FVector(Flat.X, Flat.Y, -Ball.Vel.Z * RandRange(0.35f, 0.6f));
			}
			else
			{
				Ball.Vel.Z = 0.f;
				Ball.Vel.X *= FMath::Exp(-2.2f * Dt);
				Ball.Vel.Y *= FMath::Exp(-2.2f * Dt);
			}
		}
		if (!bLive)
		{
			break;
		}

		const bool bKickPlay = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;
		// Out of bounds or abandoned.
		const bool bOut = FMath::Abs(Ball.Pos.Y) > SidelineY || FMath::Abs(Ball.Pos.X) > EndLineX;
		if (bOut || Ball.Time > 7.f)
		{
			int32 Owner = BallTeam;
			if (bKickPlay && Ball.Thrower != INDEX_NONE && !bKickPossessed)
			{
				Owner = 1 - Players[Ball.Thrower].Team;      // an untouched kick belongs to the receiving side
			}
			BallTeam = Owner;
			Ball.State = EFuryBallState::Dead;
			const bool bOwnEndZone = Ball.Pos.X * Dir(Owner) <= -GoalX;
			if (bOwnEndZone && (bKickPlay || bChangeOfPossession) && !bReturnEnteredField)
			{
				Emit(EFuryEvent::Touchback, Owner);
				DownBall(Ball.Pos.X, 0.f, TEXT("TOUCHBACK"), TEXT(""), Owner);
			}
			else if (bOwnEndZone)
			{
				Score(1 - Owner, 2, INDEX_NONE);
				PendingScoreTeam = 1 - Owner;
				Emit(EFuryEvent::Safety, 1 - Owner);
				DownBall(Ball.Pos.X, 0.f, TEXT("SAFETY"), TEXT("TWO POINTS"), 1 - Owner);
			}
			else
			{
				const float SpotX = FMath::Clamp(Ball.Pos.X, -GoalX + Yard, GoalX - Yard);
				if (!bKickPlay && Owner == Offense && !bChangeOfPossession)
				{
					FinishLooseBallDown(SpotX, Ball.Pos.Y);
				}
				else
				{
					DownBall(SpotX, Ball.Pos.Y, TEXT("OUT OF BOUNDS"), FString::Printf(TEXT("%s BALL"), *TeamInfo(Owner).Name.ToUpper()), Owner);
				}
			}
			break;
		}
		// A kick that rolls dead in the end zone is a touchback.
		if (bKickPlay && Ball.Thrower != INDEX_NONE && !bKickPossessed)
		{
			const int32 Receiving = 1 - Players[Ball.Thrower].Team;
			if (Ball.Pos.X * Dir(Receiving) < -GoalX - 30.f && Ball.Pos.Z < 40.f)
			{
				BallTeam = Receiving;
				Ball.State = EFuryBallState::Dead;
				Emit(EFuryEvent::Touchback, Receiving);
				DownBall(Ball.Pos.X, 0.f, TEXT("TOUCHBACK"), TEXT(""), Receiving);
				break;
			}
		}

		// Recovery.
		if (Ball.Pos.Z < 95.f && Ball.Time > 0.25f)
		{
			const FVector2D Flat(Ball.Pos.X, Ball.Pos.Y);
			for (int32 i = 0; i < NumPlayers; ++i)
			{
				FFurySimPlayer& P = Players[i];
				const bool bSliding = P.Act == EFuryAct::Dive && P.ActTime < 0.5f;
				if ((P.bDown && !bSliding) || P.CatchCool > 0.f || P.Engaged != INDEX_NONE)
				{
					continue;
				}
				if (FVector2D::DistSquared(P.P, Flat) > FMath::Square(P.Radius + 38.f))
				{
					continue;
				}
				P.CatchCool = 0.5f;
				if (!Chance(bSliding ? 0.95f : 0.72f))
				{
					// Booted it.
					Ball.Vel = FVector(P.V.X * 0.6f + RandRange(-200.f, 200.f), P.V.Y * 0.6f + RandRange(-200.f, 200.f), RandRange(150.f, 300.f));
					continue;
				}
				const int32 Previous = BallTeam;
				// A punt first touched by the kicking team is simply downed there.
				if (PlayType == EFuryPlayType::Punt && !bKickTouched && Ball.Thrower != INDEX_NONE && P.Team == Players[Ball.Thrower].Team)
				{
					BallTeam = 1 - P.Team;
					Ball.State = EFuryBallState::Dead;
					DownBall(Ball.Pos.X, Ball.Pos.Y, TEXT("PUNT DOWNED"), FString::Printf(TEXT("%s BALL"), *TeamInfo(BallTeam).Name.ToUpper()), BallTeam);
					break;
				}
				bKickTouched = true;
				if (!P.bDown && !bSliding)
				{
					SetAct(P, EFuryAct::PickUp, 0, 0.4f, 0.2f, false);
				}
				GiveBall(i);
				Emit(EFuryEvent::Recover, P.Team, i);
				if (!bKickPlay && P.Team != Previous)
				{
					++Teams[Previous].FumblesLost;
					AddFury(P.Team, 0.3f);
				}
				if (PlayType == EFuryPlayType::TwoPoint && P.Team != Offense)
				{
					Emit(EFuryEvent::TwoPointNoGood, P.Team);
					DownBall(P.P.X, P.P.Y, TEXT("NO GOOD"), TEXT("TWO-POINT TRY FAILS"), P.Team);
				}
				else if (bSliding)
				{
					FinishCarrierDown(i, P.P.X, P.P.Y, false, INDEX_NONE);     // fell on it
				}
				break;
			}
		}
		break;
	}

	case EFuryBallState::Dead:
		// Let an incomplete pass skid to a stop instead of freezing in mid-air.
		if (Ball.Pos.Z > BallRadius || !Ball.Vel.IsNearlyZero(1.f))
		{
			Ball.Vel.Z -= Gravity * Dt;
			Ball.Pos += Ball.Vel * Dt;
			if (Ball.Pos.Z <= BallRadius)
			{
				Ball.Pos.Z = BallRadius;
				Ball.Vel = FVector(Ball.Vel.X * FMath::Exp(-3.f * Dt), Ball.Vel.Y * FMath::Exp(-3.f * Dt), Ball.Vel.Z < -150.f ? -Ball.Vel.Z * 0.35f : 0.f);
			}
		}
		break;

	default:
		break;
	}
}

/** A loose ball went out of bounds while the offense still owned it: an ordinary dead ball at that spot. */
void FFurySim::FinishLooseBallDown(float SpotX, float SpotY)
{
	const float D = OffenseDir();
	const float Gain = (SpotX - StartLosX) * D / Yard;
	PlayYards = Gain;
	bFirstDownMade = (SpotX - FirstDownX) * D >= 0.f;
	DownBall(SpotX, SpotY, TEXT("OUT OF BOUNDS"), TEXT("FUMBLED OUT"), Offense);
}

// ---------------------------------------------------------------------------------------------
// Rules that end a live play
// ---------------------------------------------------------------------------------------------

void FFurySim::StepRules()
{
	if (Phase != EFuryPhase::Live)
	{
		return;
	}
	const int32 Carrier = CarrierIndex();
	if (Carrier != INDEX_NONE)
	{
		FFurySimPlayer& C = Players[Carrier];
		const float D = Dir(C.Team);
		if ((bKickPossessed || bChangeOfPossession) && C.P.X * D > -GoalX) { bReturnEnteredField = true; }

		// Once the ball is past the line (or in anyone's hands but the passer's) the play is "on".
		if (!bBallCrossedLine)
		{
			const bool bKickPlay = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;
			const bool bPasser = C.Team == Offense && C.Slot == 0 && !bChangeOfPossession;
			if (bKickPlay ? bKickPossessed : (!bPasser || (C.P.X - LosX) * OffenseDir() > 0.4f * Yard))
			{
				bBallCrossedLine = true;
			}
		}

		// Touchdown.
		if (C.P.X * D >= GoalX && !C.bDown)
		{
			if (PlayType == EFuryPlayType::TwoPoint)
			{
				if (C.Team == Offense)
				{
					Score(Offense, 2, Carrier);
					Emit(EFuryEvent::TwoPointGood, Offense, Carrier);
					DownBall(C.P.X, C.P.Y, TEXT("TWO POINTS!"), TEXT("CONVERSION IS GOOD"), Offense);
				}
				else
				{
					DownBall(C.P.X, C.P.Y, TEXT("NO GOOD"), TEXT(""), C.Team);
				}
				return;
			}
			const bool bFromScrimmage = C.Team == Offense && !bChangeOfPossession && PlayType == EFuryPlayType::Scrimmage;
			const float Gain = (GoalX - (bFromScrimmage ? StartLosX : ReturnStartX) * D) / Yard;
			if (C.Team == Offense && !bChangeOfPossession && PlayType == EFuryPlayType::Scrimmage)
			{
				if (bPassThrown) { Teams[Offense].PassYards += FMath::RoundToInt32(Gain); }
				else { Teams[Offense].RushYards += FMath::RoundToInt32(Gain); }
			}
			++Teams[C.Team].Touchdowns;
			Score(C.Team, 6, Carrier);
			if (C.Seat != INDEX_NONE) { ++Seats[C.Seat].Touchdowns; }
			if (bPassThrown && PassSeat != INDEX_NONE && PassSeat != C.Seat && Seats[PassSeat].Team == C.Team && !bChangeOfPossession)
			{
				++Seats[PassSeat].Touchdowns; // both seats contributed when another player caught the pass
			}
			const int32 Yards = FMath::Max(0, FMath::RoundToInt32(Gain));
			const TCHAR* Type = PlayType == EFuryPlayType::Kickoff ? TEXT("KICK RETURN") : PlayType == EFuryPlayType::Punt ? TEXT("PUNT RETURN")
				: bChangeOfPossession ? TEXT("TURNOVER RETURN") : bPassThrown ? TEXT("RECEPTION") : TEXT("RUN");
			if (Yards > Teams[C.Team].LongestTD)
			{
				Teams[C.Team].LongestTD = Yards;
				Teams[C.Team].LongestScorer = C.Roster;
				Teams[C.Team].LongestType = Type;
			}
			AddFury(C.Team, 0.12f);
			ResultTitle = TEXT("TOUCHDOWN!");
			const FFuryRosterEntry& Player = RosterOf(C);
			ResultDetail = FString::Printf(TEXT("%s   /   #%d %s   /   %d YD %s"), *TeamInfo(C.Team).Abbr, Player.Number, *Player.Name.ToUpper(), Yards, Type);
			ResultTeam = C.Team;
			BallTeam = C.Team;
			Emit(EFuryEvent::Touchdown, C.Team, Carrier, INDEX_NONE, Gain);
			BeginAfterWhistle(EFuryPhase::Celebrate, C.P);
			return;
		}

		// Stepped out.
		if (FMath::Abs(C.P.Y) > SidelineY || C.P.X * D < -EndLineX)
		{
			Emit(EFuryEvent::OutOfBounds, C.Team, Carrier);
			FinishCarrierDown(Carrier, C.P.X, FMath::Clamp(C.P.Y, -SidelineY, SidelineY), true, INDEX_NONE);
			return;
		}
	}

	// A play that somehow never ends is blown dead.
	if (LiveTime > 30.f)
	{
		UE_LOG(LogFury, Warning, TEXT("Play blown dead after 30 s (ball state %d, play type %d)"), static_cast<int32>(Ball.State), static_cast<int32>(PlayType));
		if (Carrier != INDEX_NONE)
		{
			const FFurySimPlayer& C = Players[Carrier];
			UE_LOG(LogFury, Warning, TEXT("  carrier team %d slot %d seat %d job %d act %d down %d busy %d engaged %d pos (%.0f, %.0f) vel (%.0f, %.0f) los %.0f crossed %d thrown %d kind %d scramble %d"),
				C.Team, C.Slot, C.Seat, static_cast<int32>(C.Job.Job), static_cast<int32>(C.Act), C.bDown, C.bBusy, C.Engaged, C.P.X, C.P.Y, C.V.X, C.V.Y, LosX, bBallCrossedLine, bPassThrown,
				static_cast<int32>(CurrentOff.Kind), C.bScramble);
			for (int32 i = 0; i < NumPlayers; ++i)
			{
				const FFurySimPlayer& O = Players[i];
				if (O.Team != C.Team)
				{
					UE_LOG(LogFury, Warning, TEXT("    def slot %d job %d act %d down %d busy %d engaged %d pursue %d read %.2f react %.2f pos (%.0f, %.0f) cool %.2f"),
						O.Slot, static_cast<int32>(O.Job.Job), static_cast<int32>(O.Act), O.bDown, O.bBusy, O.Engaged, O.bPursue, O.ReadLeft, O.React, O.P.X, O.P.Y, O.Cooldown);
				}
			}
		}
		if (Carrier != INDEX_NONE)
		{
			FinishCarrierDown(Carrier, Players[Carrier].P.X, Players[Carrier].P.Y, false, INDEX_NONE);
		}
		else
		{
			Ball.State = EFuryBallState::Dead;
			DownBall(FMath::Clamp(Ball.Pos.X, -GoalX + Yard, GoalX - Yard), Ball.Pos.Y, TEXT(""), TEXT(""), BallTeam);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// One step of everything that moves
// ---------------------------------------------------------------------------------------------

void FFurySim::StepLive(float Dt, const FFurySeatInput* Inputs)
{
	const bool bLive = Phase == EFuryPhase::Live;
	if (bLive)
	{
		LiveTime += Dt;
		const bool bTimed = PlayType != EFuryPlayType::ExtraPoint && PlayType != EFuryPlayType::TwoPoint;
		if (bTimed && !bOvertime && Clock > 0.f)
		{
			Clock -= Dt;
			if (Clock <= 0.f)
			{
				Clock = 0.f;
				bClockExpired = true;
			}
			if (Quarter == 4 && Clock < 30.f && !bTwoMinuteCalled)
			{
				bTwoMinuteCalled = true;
				Emit(EFuryEvent::TwoMinute);
			}
		}
	}

	// Position history, for coverage that reacts a moment late.
	TrailTimer += Dt;
	while (TrailTimer >= 1.f / 30.f)
	{
		TrailTimer -= 1.f / 30.f;
		TrailHead = (TrailHead + 1) % TrailLength;
		for (int32 i = 0; i < NumPlayers; ++i)
		{
			Trail[i][TrailHead] = Players[i].P;
		}
	}

	// The kick meter swings faster the longer the kick.
	if (bKickMeterLive && !bKickLocked)
	{
		const float KickYards = FieldGoalYards();
		KickMeter = FMath::Sin(LiveTime * (4.2f + KickYards * 0.085f));
		const int32 Kicker = Global(Offense, 0);
		if (Players[Kicker].Seat != INDEX_NONE && Inputs[Players[Kicker].Seat].A && LiveTime > 0.08f)
		{
			KickAim = KickMeter;
			bKickLocked = true;
		}
	}
	// Kickers and punters aim with the stick.
	if (Phase == EFuryPhase::PreSnap || bLive)
	{
		const int32 Kicker = Global(PlayType == EFuryPlayType::Kickoff ? KickingTeam : Offense, 0);
		if (Players[Kicker].Seat != INDEX_NONE)
		{
			KickSteer = StickToWorld(Inputs[Players[Kicker].Seat].Stick);
		}
	}

	uint8 HandledSeats = 0;
	FVector2D Wish[NumPlayers];
	float Speed[NumPlayers];
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		FFurySimPlayer& P = Players[i];
		Wish[i] = FVector2D::ZeroVector;
		Speed[i] = 0.f;
		P.ActTime += Dt;
		P.Cooldown = FMath::Max(0.f, P.Cooldown - Dt);
		P.CatchCool = FMath::Max(0.f, P.CatchCool - Dt);
		P.EvadeLeft = FMath::Max(0.f, P.EvadeLeft - Dt);
		P.StiffLeft = FMath::Max(0.f, P.StiffLeft - Dt);
		P.JumpLeft = FMath::Max(0.f, P.JumpLeft - Dt);
		P.Burst = FMath::Max(0.f, P.Burst - Dt);
		P.BurstCool = FMath::Max(0.f, P.BurstCool - Dt);
		P.bFace = false;
		if (Phase == EFuryPhase::Celebrate && PhaseTime > 1.6f && (P.Act == EFuryAct::Celebrate || P.Act == EFuryAct::Dejected))
		{
			SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
		}

		if (!P.bKeyDone && P.ActTime >= P.ActKey)
		{
			P.bKeyDone = true;
			ActKey(i);
		}
		if (P.bDown)
		{
			P.DownLeft -= Dt;
			if (P.Act == EFuryAct::Down)
			{
				// The tackled ball carrier stays put until the next play is set up.
				if (P.DownLeft <= 0.f && !P.bHasBall)
				{
					SetAct(P, EFuryAct::GetUp, P.Variant, 0.75f, 0.f, true);
				}
			}
			else if (P.ActLength > 0.f && P.ActTime >= P.ActLength)
			{
				ActEnd(i);
			}
			continue;
		}
		if (P.ActLength > 0.f && P.ActTime >= P.ActLength)
		{
			ActEnd(i);
		}
		if (P.Engaged != INDEX_NONE || P.bBusy || P.bDown)
		{
			continue;
		}
		if (P.Seat != INDEX_NONE)
		{
			// Switching to a later slot must not deliver the same press to both athletes.
			const uint8 SeatBit = 1u << P.Seat;
			if (!(HandledSeats & SeatBit))
			{
				HandledSeats |= SeatBit;
				StepHuman(P, i, Inputs[P.Seat], Dt, Wish[i], Speed[i]);
			}
		}
		else if (Phase == EFuryPhase::Live)
		{
			ThinkPlayer(P, i, Dt, Wish[i], Speed[i]);
		}
		else
		{
			ThinkAfterWhistle(P, i, Dt, Wish[i], Speed[i]);
		}
	}

	MovePlayers(Dt, Wish, Speed);
	StepEngagements(Dt);
	Separate();
	StepBall(Dt);
	if (Phase == EFuryPhase::Live || AfterWhistle())
	{
		StepContacts(Dt);
	}
	if (Phase == EFuryPhase::Live)
	{
		StepRules();
	}
}
