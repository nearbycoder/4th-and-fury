#include "FuryDirector.h"

#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "FuryAthlete.h"
#include "FuryAudio.h"
#include "FuryInput.h"
#include "FuryStadium.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

// The match as you see it: athletes, ball, markers and the broadcast camera all follow the simulation.

namespace
{
	using namespace Fury;

	FVector Smooth(const FVector& From, const FVector& To, float Rate, float Dt)
	{
		return FMath::Lerp(From, To, 1.f - FMath::Exp(-Rate * Dt));
	}
}

FFuryLook AFuryDirector::MakeLook(int32 Team, int32 Roster) const
{
	const FFuryTeam& Info = Fury::Teams()[TeamPick[Team]];
	const FFuryRosterEntry& Entry = Info.Roster[FMath::Clamp(Roster, 0, Info.Roster.Num() - 1)];
	const Fury::FKit Kit = Fury::KitFor(Info, Team == 0);
	FFuryLook Look;
	Look.Build = BuildFor(Entry.Pos);
	Look.Jersey = Kit.Jersey;
	Look.JerseyTrim = Kit.Trim;
	Look.NumberFill = Kit.NumberFill;
	Look.NumberEdge = Kit.NumberEdge;
	Look.Pants = Kit.Pants;
	Look.PantsStripe = Kit.PantsStripe;
	Look.Helmet = Kit.Helmet;
	Look.HelmetStripe = Kit.HelmetStripe;
	Look.Facemask = Kit.Facemask;
	Look.Socks = Kit.Socks;
	Look.Shoes = Kit.Shoes;
	Look.Gloves = Kit.Gloves;
	Look.Skin = Fury::SkinTones()[Entry.SkinTone];
	Look.Number = Entry.Number;
	Look.bVisor = Entry.bVisor;
	Look.Logo = TeamLogo(TeamPick[Team]);
	// Linemen stand a little taller and wider, skill players a little slighter.
	switch (Entry.Pos)
	{
	case EFuryPos::OL: case EFuryPos::DL: Look.Scale = 1.05f; break;
	case EFuryPos::WR: case EFuryPos::CB: Look.Scale = 0.98f; break;
	case EFuryPos::K: Look.Scale = 0.95f; break;
	default: Look.Scale = 1.f; break;
	}
	return Look;
}

void AFuryDirector::DressTeams()
{
	const TArray<FFuryTeam>& League = Fury::Teams();
	if (Stadium)
	{
		Stadium->Dress(League[TeamPick[0]], League[TeamPick[1]]);
	}
	// Dress both rosters now, once, so nothing has to change while the game is being played.
	for (int32 Side = 0; Side < 2 && Squad.Num() >= 2 * RosterSize; ++Side)
	{
		if (SquadLeague[Side] == TeamPick[Side])
		{
			continue;
		}
		SquadLeague[Side] = TeamPick[Side];
		for (int32 Roster = 0; Roster < RosterSize; ++Roster)
		{
			Squad[Side * RosterSize + Roster]->SetLook(MakeLook(Side, Roster));
		}
	}
}

void AFuryDirector::StartMatch()
{
	Screen = EFuryScreen::Match;
	Film.Reset();
	bViewingFilm = false;
	ScreenTime = 0.f;
	bPaused = false;
	FinalDelay = 0.f;
	HitStop = SlowMo = Shake = 0.f;

	int32 Seed = static_cast<int32>(FDateTime::Now().GetTicks() & 0x7fffffff);
	FParse::Value(FCommandLine::Get(), TEXT("FurySeed="), Seed);
	if (SoakMatches > 0) { Seed += 104729 * SoakFinished; }
	for (int32 i = 0; i < MaxSeats; ++i)
	{
		const bool bPlays = !bDemo && Seats[i].bJoined && Seats[i].Side != INDEX_NONE;
		Sim.SetSeat(i, bPlays, FMath::Max(Seats[i].Side, 0));
		Bots[i].Reset(i, Seed);
	}
	Sim.StartMatch(TeamPick[0], TeamPick[1], bQuickMatch ? 60.f : QuarterSeconds(), bQuickMatch ? 0.25f : Skill(), Seed);
	if (FParse::Param(FCommandLine::Get(), TEXT("FuryTestFury")))
	{
		// Look-development: start with the home side already in Fury.
		Sim.Teams[0].Fury = 1.f;
		Sim.Teams[0].FuryPlays = 3;
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("FuryTestFinal")))
	{
		Sim.Quarter = 4;                  // the last seconds of a close one
		Sim.Clock = 3.f;
		const int32 Box[2][4] = { { 7, 7, 0, 14 }, { 0, 10, 7, 7 } };
		for (int32 Team = 0; Team < 2; ++Team)
		{
			for (int32 Q = 0; Q < 4; ++Q)
			{
				Sim.Teams[Team].ScoreByQuarter[Q] = Box[Team][Q];
				Sim.Teams[Team].Score += Box[Team][Q];
			}
		}
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("FuryTestKick")))
	{
		Sim.DebugFieldGoal(0, 72.f);      // a 45-yard try
	}
	DressTeams();

	UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (!BallMesh && Stadium)
	{
		BallMesh = Stadium->AddMesh(TEXT("SM_Football"), FVector::ZeroVector, 0.f);
		TeeMesh = Stadium->AddMesh(TEXT("SM_KickTee"), FVector::ZeroVector, 0.f);
	}
	if (Markers.Num() == 0 && Plane)
	{
		UMaterialInterface* MarkerBase = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Fury/Materials/M_Marker.M_Marker"), nullptr, LOAD_NoWarn | LOAD_Quiet);
		auto MakeMarker = [this, Plane, MarkerBase](const FLinearColor& Color, float Inner, float Fill)
		{
			UStaticMeshComponent* Ring = NewObject<UStaticMeshComponent>(this);
			Ring->SetMobility(EComponentMobility::Movable);
			Ring->SetStaticMesh(Plane);
			Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Ring->SetCastShadow(false);
			Ring->SetupAttachment(GetRootComponent());
			Ring->SetVisibility(false);
			Ring->RegisterComponent();
			if (MarkerBase)
			{
				UMaterialInstanceDynamic* Mid = Ring->CreateDynamicMaterialInstance(0, MarkerBase);
				Mid->SetVectorParameterValue(TEXT("Color"), Color);
				Mid->SetScalarParameterValue(TEXT("Inner"), Inner);
				Mid->SetScalarParameterValue(TEXT("Fill"), Fill);
			}
			return Ring;
		};
		for (int32 i = 0; i < MaxSeats; ++i)
		{
			UStaticMeshComponent* Ring = MakeMarker(SeatColor(i), 0.72f, 0.16f);
			Markers.Add(Ring);
			MarkerMaterials.Add(Cast<UMaterialInstanceDynamic>(Ring->GetMaterial(0)));
		}
		CatchMarker = MakeMarker(FLinearColor(1.f, 0.8f, 0.13f), 0.88f, 0.f);
	}
	if (!ScrimmageLine && Cube)
	{
		UMaterialInterface* GlowBase = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Fury/Materials/M_Glow.M_Glow"), nullptr, LOAD_NoWarn | LOAD_Quiet);
		auto MakeLine = [this, Cube, GlowBase](const FLinearColor& Color, float Brightness)
		{
			UStaticMeshComponent* Line = NewObject<UStaticMeshComponent>(this);
			Line->SetMobility(EComponentMobility::Movable);
			Line->SetStaticMesh(Cube);
			Line->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Line->SetCastShadow(false);
			Line->SetupAttachment(GetRootComponent());
			Line->SetRelativeScale3D(FVector(0.14f, SidelineY * 2.f / 100.f, 0.006f));
			Line->RegisterComponent();
			if (GlowBase)
			{
				UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(GlowBase, this);
				Mid->SetVectorParameterValue(TEXT("Color"), Color);
				Mid->SetScalarParameterValue(TEXT("Brightness"), Brightness);
				Line->SetMaterial(0, Mid);
				MarkerMaterials.Add(Mid);
			}
			return Line;
		};
		ScrimmageLine = MakeLine(FLinearColor(0.08f, 0.35f, 1.f), 1.6f);
		FirstDownLine = MakeLine(FLinearColor(1.f, 0.8f, 0.05f), 1.8f);
	}

	if (BallMesh) { BallMesh->SetVisibility(true); }
	Shadows.Init(this);
	UpdateAthletes(0.f);
	Shadows.Update(Athletes, AnimSet);
	LastDrawnBall = EFuryBallState::Dead;
	CatchBlend = 0.f;
	UpdateBall(0.f);
	UpdateCamera(0.f, true);
	const FFuryTeam& Home = Sim.TeamInfo(0);
	const FFuryTeam& Away = Sim.TeamInfo(1);
	ShowBanner(FString::Printf(TEXT("%s  VS  %s"), *Home.Name.ToUpper(), *Away.Name.ToUpper()), TEXT("KICKOFF"), FLinearColor::White, 3.f, false);
	Effects.Clear();
	LastTrailPoint.Reset();
	TrailDistance = 0.f;
	FireworksLeft = 0;
	Audio->Music(TEXT(""));
	Audio->SayOneOf(TEXT("VO_Welcome"), 2, true);
	HeardPhase = Sim.Phase;
	bSaidWinner = false;
}

void AFuryDirector::GatherInput(FFurySeatInput* Out, float DeltaTime)
{
	FFuryInput& Input = FFuryInput::Get();
	for (int32 i = 0; i < MaxSeats; ++i)
	{
		Out[i] = FFurySeatInput();
		if (!Sim.Seats[i].bActive)
		{
			continue;
		}
		if (Seats[i].bBot || Seats[i].Pad == INDEX_NONE || !Input.Pad(Seats[i].Pad).bConnected)
		{
			Out[i] = Bots[i].Think(Sim, DeltaTime * TimeScale);      // fast-forwarded test runs speed the bots up too
			continue;
		}
		const FFuryPad& Pad = Input.Pad(Seats[i].Pad);
		Out[i].Stick = Pad.Stick;
		Out[i].bTurbo = Pad.Turbo();
		Out[i].A = Pad.WasPressed(EFuryButton::A);
		Out[i].B = Pad.WasPressed(EFuryButton::B);
		Out[i].X = Pad.WasPressed(EFuryButton::X);
		Out[i].Y = Pad.WasPressed(EFuryButton::Y);
		Out[i].LB = Pad.WasPressed(EFuryButton::LB);
		Out[i].RB = Pad.WasPressed(EFuryButton::RB);
		Out[i].NavX = Pad.NavX;
		Out[i].NavY = Pad.NavY;
	}
}

void AFuryDirector::OpenFilm(int32 Seat)
{
	PauseSeat = Seat;
	bViewingFilm = true;
	bFilmRolling = true;
	FilmTime = 0.f;
	Audio->Play(TEXT("SFX_UIPage"));
}

void AFuryDirector::TickFilm(const FFuryPad& Pad, float DeltaTime)
{
	if (Pad.WasPressed(EFuryButton::B) || Pad.WasPressed(EFuryButton::Y) || Pad.WasPressed(EFuryButton::Start))
	{
		bViewingFilm = false;
		if (Pad.WasPressed(EFuryButton::Start)) { bPaused = false; }
		Audio->Play(TEXT("SFX_UIBack"));
		return;
	}
	const float End = SelectedFilm().Duration();
	if (Pad.WasPressed(EFuryButton::A))
	{
		if (FilmTime >= End) { FilmTime = 0.f; }
		bFilmRolling = !bFilmRolling;
	}
	if (Pad.NavX != 0 || FMath::Abs(Pad.Stick.X) > 0.4f)
	{
		bFilmRolling = false;
		FilmTime += Pad.NavX * 0.2f + Pad.Stick.X * 2.8f * DeltaTime;
	}
	else if (bFilmRolling) { FilmTime += DeltaTime; }
	FilmTime = FMath::Clamp(FilmTime, 0.f, End);
	if (FilmTime >= End) { bFilmRolling = false; }
}

void AFuryDirector::TickPause(float DeltaTime)
{
	const FFuryPad* Pad = PauseSeat == INDEX_NONE ? nullptr : SeatPad(PauseSeat);
	if (!Pad && bTestPause) { return; }
	if (!Pad || !Pad->bConnected)
	{
		bViewingFilm = false;
		bConfirmPauseAction = false;
		bPaused = false;
		return;
	}
	if (bViewingFilm) { TickFilm(*Pad, DeltaTime); return; }
	if (bFieldGuide && !Pad->WasPressed(EFuryButton::Start))
	{
		if (Pad->WasPressed(EFuryButton::B) || Pad->WasPressed(EFuryButton::X))
		{
			bFieldGuide = false;
			Audio->Play(TEXT("SFX_UIBack"));
		}
		return;
	}
	if (!bConfirmPauseAction && Pad->WasPressed(EFuryButton::X) && !Pad->WasPressed(EFuryButton::Start))
	{
		bFieldGuide = true;
		Audio->Play(TEXT("SFX_UIPage"));
		return;
	}
	if (!bConfirmPauseAction && Pad->WasPressed(EFuryButton::Y) && Film.Last.Ready())
	{
		OpenFilm(PauseSeat);
		return;
	}
	if (Pad->WasPressed(EFuryButton::Start) || Pad->WasPressed(EFuryButton::B))
	{
		const bool bBack = bConfirmPauseAction && !Pad->WasPressed(EFuryButton::Start);
		bConfirmPauseAction = false;
		bPaused = bBack;
		Audio->Play(TEXT("SFX_UIBack"));
		return;
	}
	if (!bConfirmPauseAction)
	{
		const int32 Next = FMath::Clamp(PauseCursor - Pad->NavY, 0, FPlatformProperties::SupportsQuit() ? 4 : 3);
		if (Next != PauseCursor) { Audio->Play(TEXT("SFX_UIMove")); }
		PauseCursor = Next;
	}
	if (Pad->WasPressed(EFuryButton::A))
	{
		Audio->Play(TEXT("SFX_UISelect"));
		if (PauseCursor == 0) { bPaused = false; }
		else if (PauseCursor == 1) { OpenSettings(Seats[PauseSeat].Pad); }
		else if (PauseCursor == 4) { QuitPad = Seats[PauseSeat].Pad; }
		else if (!bConfirmPauseAction) { bConfirmPauseAction = true; }
		else if (PauseCursor == 2) { StartMatch(); }
		else { GoTo(EFuryScreen::Title); }
	}
}

void AFuryDirector::TickMatch(float DeltaTime)
{
	FFuryInput& Input = FFuryInput::Get();
	if (bDemo)
	{
		if (TryJoinFromTitle()) { return; }
	}
	else if (!bPaused)
	{
		for (int32 i = 0; i < MaxSeats; ++i)
		{
			if (Seats[i].bJoined && !Seats[i].bBot && Input.Pad(Seats[i].Pad).WasPressed(EFuryButton::Start) && Sim.Phase != EFuryPhase::GameOver)
			{
				bPaused = true;
				PauseSeat = i;
				bFieldGuide = false;
				bConfirmPauseAction = false;
				Audio->FadeFieldLoops();
				Audio->Play(TEXT("SFX_UISelect"));
				PauseCursor = 0;
				return;
			}
		}
	}
	if (bTestPause && ScreenTime > 4.f && ScreenTime < 4.2f)
	{
		bPaused = true;
		PauseSeat = 0;
		PauseCursor = 2;
	}
	if (bPaused)
	{
		Banner.Start += DeltaTime;
		TickPause(DeltaTime);
		return;
	}

	// Big hits freeze the frame for an instant, then play out in slow motion.
	float Dt = FMath::Min(DeltaTime, 0.05f) * TimeScale;
	if (HitStop > 0.f)
	{
		HitStop -= DeltaTime;
		Dt = 0.f;
	}
	else if (SlowMo > 0.f)
	{
		SlowMo -= DeltaTime;
		Dt *= 0.35f;
	}

	FFurySeatInput In[MaxSeats];
	GatherInput(In, DeltaTime);
	float Remaining = Dt;
	while (Remaining > 1.e-5f)
	{
		const float Step = FMath::Min(Remaining, 1.f / 90.f);
		Sim.Step(Step, In);
		if (!bDemo) { Film.Record(Sim); }
		Remaining -= Step;
		// Button presses count once, however many steps the frame is split into.
		for (FFurySeatInput& Seat : In)
		{
			Seat.A = Seat.B = Seat.X = Seat.Y = Seat.LB = Seat.RB = false;
			Seat.NavX = Seat.NavY = 0;
		}
		HandleEvents();
	}

	UpdateAthletes(Dt);
	Shadows.Update(Athletes, AnimSet);
	UpdateBall(Dt);
	UpdateMarkers();
	UpdateCamera(DeltaTime, false);
	UpdateEffects(Dt);

	TickMatchSounds(DeltaTime);

	// The crowd settles between plays and stays loud while a team is in Fury.
	float Floor = Sim.Phase == EFuryPhase::Live ? 0.4f : 0.22f;
	const int32 Runner = Sim.CarrierIndex();
	if (Sim.Phase == EFuryPhase::Live && Runner != INDEX_NONE)
	{
		const FFurySimPlayer& P = Sim.Players[Runner];
		const float NearGoal = FMath::Clamp((Fury::YardLine(P.Team, P.P.X) - 70.f) / 30.f, 0.f, 1.f);
		Floor += 0.45f * NearGoal;
	}
	if (Sim.Teams[0].InFury() || Sim.Teams[1].InFury()) { Floor = FMath::Max(Floor, 0.7f); }
	Excitement = FMath::Max(Floor, Excitement - DeltaTime * 0.12f);
	if (Stadium) { Stadium->SetExcitement(Excitement); }

	if (Sim.Phase == EFuryPhase::GameOver)
	{
		FinalDelay += DeltaTime;
		if (FinalDelay > 3.4f && !bSaidWinner)
		{
			bSaidWinner = true;
			if (Sim.Winner() != INDEX_NONE) { Audio->Say(Sim.Winner() == 0 ? TEXT("VO_Win_Home") : TEXT("VO_Win_Away"), true); }
		}
		if (FinalDelay > 7.f)
		{
			GoTo(bDemo ? EFuryScreen::Title : EFuryScreen::Final);
		}
	}
}

void AFuryDirector::TickMatchSounds(float DeltaTime)
{
	// Sound that follows the state of play rather than single events.
	const bool bHalftime = Sim.Phase == EFuryPhase::Break && Sim.Quarter == 3;
	const bool bChoosing = Sim.Phase == EFuryPhase::PlaySelect || Sim.Phase == EFuryPhase::PatSelect;
	Audio->Music(bHalftime ? TEXT("MUS_Halftime") : bChoosing ? TEXT("MUS_PlaySelect") : TEXT(""), bHalftime ? 0.5f : 0.32f);
	const bool bLive = Sim.Phase == EFuryPhase::Live;
	const bool bAirborne = Sim.Ball.State == EFuryBallState::Pass || Sim.Ball.State == EFuryBallState::Kick || Sim.Ball.State == EFuryBallState::FieldGoal;
	const float Flight = FMath::Clamp(Sim.Ball.Time / FMath::Max(Sim.Ball.Duration, 0.01f), 0.f, 1.f);
	const float Approach = FMath::Square(Flight);
	Audio->SetLoop(TEXT("SFX_BallAir"), bAirborne && bLive, 0.18f + 0.27f * Approach, 0.94f + 0.28f * Approach);
	Audio->SetLoop(TEXT("SFX_FuryLoop"), Sim.Teams[0].InFury() || Sim.Teams[1].InFury(), 0.45f);

	// Cleats on turf under whoever has the ball.
	const int32 Carrier = Sim.CarrierIndex();
	const float CarrierSpeed = (bLive && Carrier != INDEX_NONE && Sim.Players[Carrier].Height < 5.f && !Sim.Players[Carrier].bDown) ? Sim.Players[Carrier].V.Size() : 0.f;
	if (CarrierSpeed > 260.f && Athlete(Carrier) && Athlete(Carrier)->Stepped())
	{
		Audio->PlayOneOf(TEXT("SFX_Cleat"), 6, FMath::Clamp(CarrierSpeed / 1800.f, 0.2f, 0.6f), 0.1f);
	}

	// The crowd gets a chant going before the snaps that matter.
	const bool bBigDown = Sim.PlayType == EFuryPlayType::TwoPoint || (Sim.PlayType == EFuryPlayType::Scrimmage && (Sim.Down >= 3 || Sim.GoalToGo()));
	Audio->SetLoop(TEXT("AMB_Chant"), bBigDown && (Sim.Phase == EFuryPhase::Lineup || Sim.Phase == EFuryPhase::PreSnap), 0.42f);

	// Play calling: the cursor ticks, the page turns, and the clock nags at the end.
	if (Sim.Phase != HeardPhase)
	{
		if (HeardPhase == EFuryPhase::Break && Sim.Quarter == 3 && Sim.Phase != EFuryPhase::GameOver)
		{
			Audio->Say(TEXT("VO_Quarter3"), true);
		}
		HeardPhase = Sim.Phase;
		HeardPick[0] = Sim.Picks[0];
		HeardPick[1] = Sim.Picks[1];
		HeardPat = Sim.PatChoice;
		HeardSecond = FMath::CeilToInt32(Sim.SelectTimer);
		HeardMeter = Sim.KickMeter;
		HeardMeterStep = 0.f;
	}
	if (Sim.Phase == EFuryPhase::PlaySelect)
	{
		bool bWaiting = false;
		for (int32 Team = 0; Team < 2; ++Team)
		{
			const FFuryPick& Pick = Sim.Picks[Team];
			if (Sim.Captain(Team) == INDEX_NONE)
			{
				continue;
			}
			bWaiting |= !Pick.bLocked;
			if (Pick.Page != HeardPick[Team].Page) { Audio->Play(TEXT("SFX_UIPage")); }
			else if (Pick.Cursor != HeardPick[Team].Cursor) { Audio->Play(TEXT("SFX_UIMove"), 0.7f); }
			else if (Pick.bFlip != HeardPick[Team].bFlip) { Audio->Play(TEXT("SFX_UIMove"), 0.7f, 1.3f); }
			HeardPick[Team] = Pick;
		}
		const int32 Second = FMath::CeilToInt32(Sim.SelectTimer);
		if (Second != HeardSecond && Second <= 3 && Second >= 1 && bWaiting)
		{
			Audio->Play(TEXT("SFX_Countdown"), 0.8f);
		}
		HeardSecond = Second;
	}
	else if (Sim.Phase == EFuryPhase::PatSelect && Sim.PatChoice != HeardPat)
	{
		HeardPat = Sim.PatChoice;
		Audio->Play(TEXT("SFX_UIMove"), 0.7f);
	}

	// The kick meter ticks through the sweet spot and knocks at each end.
	if (Sim.bKickMeterLive && !Sim.bKickLocked)
	{
		const float Step = Sim.KickMeter - HeardMeter;
		if ((Sim.KickMeter > 0.f) != (HeardMeter > 0.f)) { Audio->Play(TEXT("SFX_MeterTick"), 0.9f, 1.25f); }
		else if (Step * HeardMeterStep < 0.f) { Audio->Play(TEXT("SFX_MeterTick"), 0.6f, 0.8f); }
		if (Step != 0.f) { HeardMeterStep = Step; }
	}
	HeardMeter = Sim.KickMeter;
}

void AFuryDirector::HandleEvents()
{
	const FLinearColor White(1.f, 1.f, 1.f);
	auto TeamColor = [this](int32 Team) { return Team == INDEX_NONE ? FLinearColor::White : Sim.TeamInfo(Team).Primary; };
	auto TeamName = [this](int32 Team) { return Team == INDEX_NONE ? FString() : Sim.TeamInfo(Team).Name.ToUpper(); };
	for (const FFuryEvent& Event : Sim.Events)
	{
		const FVector At(Event.Pos.X, Event.Pos.Y, Event.Other != INDEX_NONE && Event.Pos.Z > 0.f ? Event.Pos.Z : 95.f);
		const FLinearColor Flash(1.f, 0.93f, 0.7f);

		// What it sounds and looks like.
		switch (Event.Type)
		{
		case EFuryEvent::Hut: Audio->PlayOneOf(TEXT("SFX_Hut"), 3, 0.6f); break;
		case EFuryEvent::Snap: Audio->Play(TEXT("SFX_Snap"), 0.8f); break;
		case EFuryEvent::Throw: Audio->PlayOneOf(TEXT("SFX_Throw"), 2, 0.8f); break;
		case EFuryEvent::Catch:
			Audio->PlayOneOf(TEXT("SFX_Catch"), 3, 0.9f);
			Effects.Burst(At + FVector(0.f, 0.f, 30.f), Flash, 6, 180.f, 0.18f, 26.f, 2.f, 200.f);
			if (Event.Value >= 20.f) { Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 0.7f); Audio->SayOneOf(TEXT("VO_BigGain"), 3); }
			break;
		case EFuryEvent::Drop: case EFuryEvent::Tip: Audio->Play(TEXT("SFX_Drop"), 0.8f); break;
		case EFuryEvent::Incomplete: Audio->Play(TEXT("SFX_Bounce"), 0.6f); Audio->SayOneOf(TEXT("VO_Incomplete"), 3); break;
		case EFuryEvent::Intercept:
			Audio->Play(TEXT("SFX_Turnover")); Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 0.9f); Audio->SayOneOf(TEXT("VO_Interception"), 3, true);
			Effects.Burst(At + FVector(0.f, 0.f, 60.f), FLinearColor(0.5f, 0.8f, 1.f), 26, 420.f, 0.5f, 34.f, 4.f);
			break;
		case EFuryEvent::Tackle:
			Audio->PlayOneOf(TEXT("SFX_Hit"), 4, 0.55f + 0.45f * Event.Value);
			if (Sparkle.FRand() < 0.4f) { Audio->PlayOneOf(TEXT("SFX_Grunt"), 4, 0.5f); }
			Effects.Burst(At, Flash, 8 + FMath::RoundToInt32(10.f * Event.Value), 260.f + 240.f * Event.Value, 0.3f, 22.f, 2.2f, 620.f);
			Effects.Burst(FVector(At.X, At.Y, 8.f), FLinearColor(0.35f, 0.5f, 0.3f), 10, 200.f, 0.5f, 16.f, 0.8f, 700.f, 0.7f);
			break;
		case EFuryEvent::BigHit:
			Audio->PlayOneOf(TEXT("SFX_BigHit"), 3, 1.f); Audio->PlayOneOf(TEXT("AMB_Ooh"), 2, 0.9f);
			if (Sparkle.FRand() < 0.45f) { Audio->SayOneOf(TEXT("VO_BigHit"), 4); }
			Effects.Emit(At, FVector::ZeroVector, FLinearColor::White, 0.14f, 260.f, 5.f, 0.f, 0.f, 1800.f);
			Effects.Burst(At, FLinearColor(1.f, 0.8f, 0.35f), 44, 760.f, 0.55f, 30.f, 4.5f, 700.f);
			Effects.Burst(FVector(At.X, At.Y, 8.f), FLinearColor(0.35f, 0.5f, 0.3f), 22, 340.f, 0.7f, 18.f, 0.9f, 700.f, 0.7f);
			break;
		case EFuryEvent::Sack: Audio->Play(TEXT("SFX_Sack")); Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 0.8f); Audio->SayOneOf(TEXT("VO_Sack"), 3, true); break;
		case EFuryEvent::Fumble:
			Audio->Play(TEXT("SFX_Fumble")); Audio->SayOneOf(TEXT("VO_Fumble"), 2, true);
			Effects.Burst(At, FLinearColor(1.f, 0.85f, 0.1f), 24, 420.f, 0.45f, 28.f, 4.f);
			break;
		case EFuryEvent::Recover: Audio->PlayOneOf(TEXT("SFX_Catch"), 3, 0.8f); break;
		case EFuryEvent::BrokenTackle: Audio->PlayOneOf(TEXT("SFX_Hit"), 4, 0.45f); Audio->PlayOneOf(TEXT("SFX_Grunt"), 4, 0.5f); break;
		case EFuryEvent::StiffArm: case EFuryEvent::Shove: case EFuryEvent::Pancake:
			Audio->Play(TEXT("SFX_StiffArm"), 0.9f);
			Effects.Burst(At, Flash, 12, 380.f, 0.28f, 24.f, 2.6f, 500.f);
			break;
		case EFuryEvent::Spin: Audio->Play(TEXT("SFX_Spin"), 0.7f); break;
		case EFuryEvent::Juke: Audio->Play(TEXT("SFX_Juke"), 0.7f); Effects.Burst(FVector(At.X, At.Y, 6.f), FLinearColor(0.35f, 0.5f, 0.3f), 8, 220.f, 0.4f, 14.f, 0.8f, 600.f, 0.6f); break;
		case EFuryEvent::Hurdle: Audio->Play(TEXT("SFX_Spin"), 0.6f, 1.25f); break;
		case EFuryEvent::Dive:
			Audio->PlayOneOf(TEXT("SFX_Dive"), 2, 0.7f);
			Effects.Burst(FVector(At.X, At.Y, 6.f), FLinearColor(0.35f, 0.5f, 0.3f), 12, 260.f, 0.5f, 16.f, 0.8f, 600.f, 0.6f);
			break;
		case EFuryEvent::LateHit:
		{
			const bool bHeavy = Event.Value >= 0.85f;
			if (bHeavy) { Audio->PlayOneOf(TEXT("SFX_BigHit"), 3, 0.85f); }
			else { Audio->PlayOneOf(TEXT("SFX_Hit"), 4, 0.75f); }
			Audio->PlayOneOf(TEXT("AMB_Ooh"), 2, bHeavy ? 0.7f : 0.4f);
			Effects.Burst(At, bHeavy ? FLinearColor(1.f, 0.72f, 0.28f) : Flash, bHeavy ? 18 : 9, bHeavy ? 500.f : 310.f, 0.23f, 19.f, 2.4f, 600.f);
			Effects.Burst(FVector(At.X, At.Y, 6.f), FLinearColor(0.32f, 0.46f, 0.24f), bHeavy ? 10 : 5, 220.f, 0.35f, 14.f, 0.85f, 660.f);
			Shake = FMath::Max(Shake, bHeavy ? 0.38f : 0.17f);
			break;
		}
		case EFuryEvent::Touchdown:
			Audio->Play(TEXT("SFX_Touchdown")); Audio->Play(TEXT("SFX_Cannon"), 0.8f); Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 1.f); Audio->SayOneOf(TEXT("VO_Touchdown"), 4, true);
			FireworksLeft = 10;
			FireworkTimer = 0.2f;
			FireworkTeam = Event.Team;
			break;
		case EFuryEvent::FirstDown: Audio->Play(TEXT("SFX_FirstDown"), 0.8f); Audio->SayOneOf(TEXT("VO_FirstDown"), 3); break;
		case EFuryEvent::TurnoverOnDowns: Audio->Play(TEXT("SFX_Turnover"), 0.8f); Audio->Say(TEXT("VO_Turnover"), true); break;
		case EFuryEvent::Safety: Audio->Play(TEXT("SFX_Turnover")); Audio->Say(TEXT("VO_Safety"), true); break;
		case EFuryEvent::Whistle: Audio->Play(TEXT("SFX_Whistle"), 0.7f); break;
		case EFuryEvent::Kickoff: Audio->PlayOneOf(TEXT("SFX_Kick"), 2); Audio->SayOneOf(TEXT("VO_Kickoff"), 2); Effects.Burst(FVector(At.X, At.Y, 8.f), FLinearColor(0.35f, 0.5f, 0.3f), 14, 300.f, 0.5f, 16.f, 0.8f, 600.f, 0.6f); break;
		case EFuryEvent::PuntKick: Audio->PlayOneOf(TEXT("SFX_Kick"), 2); Audio->Say(TEXT("VO_Punt")); break;
		case EFuryEvent::FieldGoalKick: Audio->PlayOneOf(TEXT("SFX_Kick"), 2); break;
		case EFuryEvent::FieldGoalGood: Audio->Play(TEXT("SFX_FieldGoalGood")); Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 0.8f); Audio->Say(TEXT("VO_FieldGoalGood"), true); break;
		case EFuryEvent::FieldGoalNoGood: Audio->Play(TEXT("SFX_NoGood")); Audio->Play(TEXT("AMB_Boo"), 0.7f); Audio->Say(TEXT("VO_FieldGoalNoGood"), true); break;
		case EFuryEvent::ExtraPointGood: Audio->Play(TEXT("SFX_FieldGoalGood"), 0.6f); Audio->Say(TEXT("VO_ExtraPointGood")); break;
		case EFuryEvent::ExtraPointNoGood: Audio->Play(TEXT("SFX_NoGood")); Audio->Play(TEXT("AMB_Boo"), 0.7f); break;
		case EFuryEvent::TwoPointGood: Audio->Play(TEXT("SFX_FieldGoalGood")); Audio->PlayOneOf(TEXT("AMB_Cheer"), 3, 0.9f); Audio->Say(TEXT("VO_TwoPointGood"), true); break;
		case EFuryEvent::TwoPointNoGood: Audio->Play(TEXT("SFX_NoGood")); Audio->Say(TEXT("VO_TwoPointNoGood"), true); break;
		case EFuryEvent::Doink: Audio->Play(TEXT("SFX_Goalpost")); break;
		case EFuryEvent::FuryStart: Audio->Play(TEXT("SFX_FuryIgnite")); Audio->SayOneOf(TEXT("VO_Fury"), 3, true); break;
		case EFuryEvent::FuryEnd: Audio->Play(TEXT("SFX_FuryEnd"), 0.8f); break;
		case EFuryEvent::PlayPicked: Audio->Play(TEXT("SFX_PlayPicked"), 0.7f); break;
		case EFuryEvent::QuarterEnd:
			Audio->Play(TEXT("SFX_Horn"));
			Audio->Play(TEXT("SFX_WhistleLong"), 0.7f);
			if (Event.Value < 1.5f) { Audio->Say(TEXT("VO_Quarter2"), true); }
			else if (Event.Value > 2.5f && Event.Value < 3.5f) { Audio->Say(TEXT("VO_Quarter4"), true); }
			break;
		case EFuryEvent::Halftime: Audio->Say(TEXT("VO_Halftime"), true); break;
		case EFuryEvent::Overtime: Audio->Say(TEXT("VO_Overtime"), true); break;
		case EFuryEvent::TwoMinute: Audio->Say(TEXT("VO_TwoMinute"), true); break;
		case EFuryEvent::GameOver:
			Audio->Play(TEXT("MUS_Victory"), 0.7f);
			Audio->SayOneOf(TEXT("VO_Final"), 2, true);
			FireworksLeft = 14;
			FireworkTimer = 0.4f;
			FireworkTeam = Event.Team == INDEX_NONE ? 0 : Event.Team;
			break;
		default: break;
		}

		// What it says on screen.
		switch (Event.Type)
		{
		case EFuryEvent::Touchdown:
			ShowBanner(TEXT("TOUCHDOWN!"), Sim.ResultDetail, TeamColor(Event.Team), 2.8f, true);
			Excitement = 1.f;
			Shake = FMath::Max(Shake, 0.5f);
			break;
		case EFuryEvent::FirstDown:
			ShowBanner(TEXT("FIRST DOWN"), TeamName(Event.Team), TeamColor(Event.Team), 1.7f, false);
			Excitement = FMath::Max(Excitement, 0.6f);
			break;
		case EFuryEvent::Sack:
			ShowBanner(TEXT("SACKED!"), TeamName(Event.Team), TeamColor(Event.Team), 2.2f, true);
			Excitement = FMath::Max(Excitement, 0.8f);
			break;
		case EFuryEvent::Intercept:
			ShowBanner(TEXT("PICKED OFF!"), TeamName(Event.Team), TeamColor(Event.Team), 2.4f, true);
			Excitement = 0.95f;
			break;
		case EFuryEvent::Fumble:
			ShowBanner(TEXT("FUMBLE!"), TEXT("LOOSE BALL"), FLinearColor(1.f, 0.8f, 0.1f), 1.6f, true);
			Excitement = 0.9f;
			break;
		case EFuryEvent::Recover:
			ShowBanner(TEXT("RECOVERED"), TeamName(Event.Team), TeamColor(Event.Team), 1.6f, false);
			break;
		case EFuryEvent::Incomplete:
			ShowBanner(TEXT("INCOMPLETE"), TEXT(""), FLinearColor(0.7f, 0.72f, 0.75f), 1.3f, false);
			break;
		case EFuryEvent::BigHit:
			Shake = FMath::Max(Shake, 0.75f);
			HitStop = 0.07f;
			SlowMo = 0.22f;
			Excitement = FMath::Max(Excitement, 0.75f);
			break;
		case EFuryEvent::Tackle:
			Shake = FMath::Max(Shake, 0.18f + 0.25f * Event.Value);
			break;
		case EFuryEvent::StiffArm: case EFuryEvent::Pancake: case EFuryEvent::Shove:
			Shake = FMath::Max(Shake, 0.3f);
			break;
		case EFuryEvent::FuryStart:
			ShowBanner(TEXT("FURY!"), TeamName(Event.Team) + TEXT(" UNLEASHED"), FLinearColor(1.f, 0.35f, 0.05f), 3.f, true);
			Excitement = 1.f;
			Shake = FMath::Max(Shake, 0.6f);
			break;
		case EFuryEvent::FieldGoalGood:
			ShowBanner(TEXT("IT'S GOOD!"), TEXT("FIELD GOAL"), TeamColor(Event.Team), 2.4f, true);
			Excitement = 0.85f;
			break;
		case EFuryEvent::FieldGoalNoGood: case EFuryEvent::ExtraPointNoGood:
			ShowBanner(TEXT("NO GOOD!"), TEXT(""), FLinearColor(0.75f, 0.2f, 0.15f), 2.f, true);
			break;
		case EFuryEvent::ExtraPointGood:
			ShowBanner(TEXT("EXTRA POINT"), TEXT("GOOD"), TeamColor(Event.Team), 1.6f, false);
			break;
		case EFuryEvent::TwoPointGood:
			ShowBanner(TEXT("TWO POINTS!"), TeamName(Event.Team), TeamColor(Event.Team), 2.4f, true);
			Excitement = 0.95f;
			break;
		case EFuryEvent::TwoPointNoGood:
			ShowBanner(TEXT("DENIED!"), TEXT("NO CONVERSION"), TeamColor(Event.Team), 2.f, true);
			break;
		case EFuryEvent::Safety:
			ShowBanner(TEXT("SAFETY!"), TEXT("TWO POINTS"), TeamColor(Event.Team), 2.6f, true);
			Excitement = 0.95f;
			break;
		case EFuryEvent::TurnoverOnDowns:
			ShowBanner(TEXT("TURNOVER ON DOWNS"), TeamName(Event.Team) + TEXT(" BALL"), TeamColor(Event.Team), 2.2f, false);
			break;
		case EFuryEvent::Touchback:
			ShowBanner(TEXT("TOUCHBACK"), TEXT(""), White, 1.5f, false);
			break;
		case EFuryEvent::Halftime:
			ShowBanner(TEXT("HALFTIME"), FString::Printf(TEXT("%s %d  -  %s %d"), *Sim.TeamInfo(0).Abbr, Sim.Teams[0].Score, *Sim.TeamInfo(1).Abbr, Sim.Teams[1].Score), White, 5.f, true);
			break;
		case EFuryEvent::QuarterEnd:
			if (Event.Value < 1.5f || (Event.Value > 2.5f && Event.Value < 3.5f))
			{
				ShowBanner(FString::Printf(TEXT("END OF QUARTER %d"), FMath::RoundToInt32(Event.Value)), TEXT(""), White, 2.6f, false);
			}
			break;
		case EFuryEvent::Overtime:
			ShowBanner(TEXT("SUDDEN DEATH"), TEXT("NEXT SCORE WINS"), FLinearColor(1.f, 0.3f, 0.1f), 3.4f, true);
			break;
		case EFuryEvent::GameOver:
			ShowBanner(TEXT("FINAL"), Event.Team == INDEX_NONE ? FString(TEXT("TIE GAME")) : TeamName(Event.Team) + TEXT(" WIN"), TeamColor(Event.Team), 6.f, true);
			Excitement = 1.f;
			break;
		case EFuryEvent::TwoMinute:
			ShowBanner(TEXT("30 SECONDS"), TEXT("LAST CHANCE"), FLinearColor(1.f, 0.8f, 0.1f), 2.f, false);
			break;
		case EFuryEvent::Catch:
			if (Event.Value >= 20.f) { Excitement = FMath::Max(Excitement, 0.75f); }
			break;
		default:
			break;
		}
	}
	Sim.Events.Reset();
}

void AFuryDirector::UpdateAthletes(float DeltaTime)
{
	// The unit on the field changes between offense, defense and the kicking game. Every roster
	// member already has a dressed body, so a change of unit is only a change of who is shown.
	uint32 OnField = 0;
	for (int32 i = 0; i < NumPlayers && i < Athletes.Num(); ++i)
	{
		const FFurySimPlayer& P = Sim.Players[i];
		const int32 Member = P.Team * RosterSize + FMath::Clamp(P.Roster, 0, RosterSize - 1);
		if (Squad.IsValidIndex(Member))
		{
			Athletes[i] = Squad[Member];
			OnField |= 1u << Member;
		}
		AFuryAthlete* Athlete = Athletes[i];
		FFuryAthleteState State;
		State.Pos = P.P;
		State.Height = P.Height;
		State.Yaw = P.Yaw;
		State.Vel = P.V;
		State.Act = P.Act;
		State.Variant = P.Variant;
		State.ActSerial = P.ActSerial;
		State.ActTime = P.ActTime;
		State.ActLength = P.ActLength;
		State.ActKey = P.ActKey;
		State.bHasBall = P.bHasBall;
		State.bPasser = Sim.IsPasser(i);
		State.bFury = Sim.Teams[P.Team].InFury();
		Athlete->Advance(State, DeltaTime);
	}
	for (int32 Member = 0; Member < Squad.Num(); ++Member)
	{
		if ((OnField & (1u << Member)) == 0)
		{
			Squad[Member]->SetActorHiddenInGame(true);
		}
	}
}

void AFuryDirector::UpdateBall(float DeltaTime)
{
	if (!BallMesh)
	{
		return;
	}
	const FFuryBall& Ball = Sim.Ball;
	FVector Location = Ball.Pos;
	FQuat Rotation = FQuat::Identity;
	const FVector Flat(Ball.Vel.X, Ball.Vel.Y, 0.f);

	switch (Ball.State)
	{
	case EFuryBallState::Held:
		if (Athletes.IsValidIndex(Ball.Holder))
		{
			AFuryAthlete* Holder = Athletes[Ball.Holder];
			const EFuryGrip Grip = Holder->CurrentGrip() == EFuryGrip::None ? EFuryGrip::Hand : Holder->CurrentGrip();
			const FTransform Socket = Holder->GripWorld(Grip);
			Location = Socket.GetLocation();
			Rotation = Socket.GetRotation();
			if (LastDrawnBall == EFuryBallState::Pass)
			{
				// Bridge the last flight sample to the receiver's animated hands.
				CatchOffset = (BallMesh->GetComponentLocation() - Location).GetClampedToMaxSize(100.f);
				CatchBlend = 0.09f;
			}
			CatchBlend = FMath::Max(0.f, CatchBlend - DeltaTime);
			Location += CatchOffset * FMath::SmoothStep(0.f, 0.09f, CatchBlend);
		}
		break;
	case EFuryBallState::Pass:
	{
		if (LastDrawnBall != EFuryBallState::Pass)
		{
			ReleaseOffset = FVector::ZeroVector;
			if (Athletes.IsValidIndex(Ball.Thrower))
			{
				ReleaseOffset = (Athletes[Ball.Thrower]->GripWorld(EFuryGrip::Hand).GetLocation() - Ball.From).GetClampedToMaxSize(110.f);
			}
		}
		Location += ReleaseOffset * (1.f - FMath::SmoothStep(0.f, 0.14f, Ball.Time));
		// A spiral: nose along the flight path, spinning about its long axis.
		const FVector Dir = Ball.Vel.GetSafeNormal();
		const float Wobble = Ball.bTipped ? 6.f : 0.f;
		Rotation = FRotationMatrix::MakeFromX(Dir).ToQuat() * FQuat(FVector::ForwardVector, Ball.Spin * 2.2f) * FQuat(FVector::RightVector, Ball.Spin * Wobble);
		break;
	}
	case EFuryBallState::Kick:
	case EFuryBallState::FieldGoal:
	{
		// End over end.
		const FVector Dir = Flat.GetSafeNormal();
		Rotation = FRotationMatrix::MakeFromX(Dir.IsNearlyZero() ? FVector::ForwardVector : Dir).ToQuat() * FQuat(FVector::RightVector, -Ball.Spin * 0.9f);
		break;
	}
	case EFuryBallState::Loose:
	case EFuryBallState::Dead:
	{
		const float Speed = Ball.Vel.Size();
		BallSpin.Pitch += Speed * DeltaTime * 0.7f;
		BallSpin.Yaw += Speed * DeltaTime * 0.25f;
		Rotation = FQuat(BallSpin);
		break;
	}
	case EFuryBallState::Snap:
		Rotation = FRotationMatrix::MakeFromX(FVector(Sim.OffenseDir(), 0.f, 0.f)).ToQuat() * FQuat(FVector::ForwardVector, Ball.Spin * 2.f);
		break;
	case EFuryBallState::Tee:
		if (Sim.PlayType == EFuryPlayType::Kickoff)
		{
			Location.Z = 22.f;
			Rotation = FQuat(FRotator(72.f, Dir(Sim.KickingTeam) > 0.f ? 0.f : 180.f, 0.f));      // propped up on the tee
		}
		else if (Sim.PlayType == EFuryPlayType::FieldGoal || Sim.PlayType == EFuryPlayType::ExtraPoint)
		{
			Location.Z = Sim.Phase == EFuryPhase::Live ? 14.f : 9.f;
			Rotation = Sim.Phase == EFuryPhase::Live ? FQuat(FRotator(80.f, 0.f, 0.f)) : FQuat(FRotator(0.f, 90.f, 0.f));
		}
		else
		{
			Location.Z = 9.f;
			Rotation = FQuat(FRotator(0.f, 0.f, 0.f));
		}
		break;
	}
	LastDrawnBall = Ball.State;
	BallMesh->SetWorldLocationAndRotation(Location, Rotation);

	if (TeeMesh)
	{
		const bool bTee = Sim.PlayType == EFuryPlayType::Kickoff && (Sim.Phase == EFuryPhase::Lineup || Sim.Phase == EFuryPhase::PreSnap || Ball.State == EFuryBallState::Tee);
		TeeMesh->SetVisibility(bTee);
		if (bTee)
		{
			TeeMesh->SetWorldLocation(FVector(Sim.LosX, 0.f, 0.f));
		}
	}
}

void AFuryDirector::UpdateMarkers()
{
	const float Time = GetWorld()->GetTimeSeconds();
	for (int32 i = 0; i < Markers.Num(); ++i)
	{
		const FFurySeat& Seat = Sim.Seats[i];
		const bool bShow = Seat.bActive && Seat.Player != INDEX_NONE && Sim.Phase != EFuryPhase::GameOver;
		Markers[i]->SetVisibility(bShow);
		if (!bShow)
		{
			continue;
		}
		const FFurySimPlayer& P = Sim.Players[Seat.Player];
		const float Pulse = P.bHasBall ? 1.f + 0.12f * FMath::Sin(Time * 9.f) : 1.f;
		Markers[i]->SetWorldLocation(FVector(P.P.X, P.P.Y, 2.5f));
		const float Ring = Sim.AfterWhistle() ? 1.06f : 1.75f * Pulse;
		Markers[i]->SetWorldScale3D(FVector(Ring, Ring, 1.f));
		if (MarkerMaterials.IsValidIndex(i) && MarkerMaterials[i])
		{
			MarkerMaterials[i]->SetScalarParameterValue(TEXT("Fill"), Sim.AfterWhistle() ? 0.035f : P.bHasBall ? 0.4f : 0.16f);
		}
	}

	// A narrowing gold ring gives returners and receivers a catch point while the ball is aloft.
	if (CatchMarker)
	{
		const FFuryBall& Ball = Sim.Ball;
		const bool bFlight = Ball.State == EFuryBallState::Kick || Ball.State == EFuryBallState::Pass;
		const bool bShow = Sim.Phase == EFuryPhase::Live && bFlight && !Ball.bTipped && Ball.Time < Ball.Duration;
		CatchMarker->SetVisibility(bShow);
		if (bShow)
		{
			const float Remaining = 1.f - Ball.Time / Ball.Duration;
			const float Diameter = 1.4f + 1.8f * Remaining;
			CatchMarker->SetWorldLocation(FVector(Ball.To.X, Ball.To.Y, 3.5f));
			CatchMarker->SetWorldScale3D(FVector(Diameter, Diameter, 1.f));
		}
	}

	// The line of scrimmage and the line to gain, the way television draws them.
	const bool bScrimmage = Sim.PlayType == EFuryPlayType::Scrimmage || Sim.PlayType == EFuryPlayType::Punt || Sim.PlayType == EFuryPlayType::FieldGoal;
	const bool bLines = bScrimmage && (Sim.Phase == EFuryPhase::PlaySelect || Sim.Phase == EFuryPhase::Lineup || Sim.Phase == EFuryPhase::PreSnap || Sim.Phase == EFuryPhase::Live);
	if (Stadium) { Stadium->SetChains(bScrimmage ? Sim.Down : 0, Sim.LosX, Sim.FirstDownX, Sim.OffenseDir(), Sim.GoalToGo()); }
	if (ScrimmageLine)
	{
		ScrimmageLine->SetVisibility(bLines);
		ScrimmageLine->SetWorldLocation(FVector(Sim.LosX, 0.f, 0.7f));
	}
	if (FirstDownLine)
	{
		FirstDownLine->SetVisibility(bLines && !Sim.GoalToGo());
		FirstDownLine->SetWorldLocation(FVector(Sim.FirstDownX, 0.f, 0.7f));
	}
}

void AFuryDirector::UpdateCamera(float DeltaTime, bool bSnap)
{
	// A sideline broadcast camera on the +Y side. Each frame it works out which athletes matter,
	// then picks the tightest shot that still shows all of them: wide before the snap so the whole
	// formation is readable, close on a runner, stretched out along a long pass.
	const FFuryBall& Ball = Sim.Ball;
	const int32 Carrier = Sim.CarrierIndex();
	FVector2D Min(1.e9f, 1.e9f), Max(-1.e9f, -1.e9f);
	auto Include = [&Min, &Max](const FVector2D& Point, float Pad)
	{
		Min.X = FMath::Min(Min.X, Point.X - Pad); Min.Y = FMath::Min(Min.Y, Point.Y - Pad);
		Max.X = FMath::Max(Max.X, Point.X + Pad); Max.Y = FMath::Max(Max.Y, Point.Y + Pad);
	};
	const FVector2D BallFlat(Ball.Pos.X, Ball.Pos.Y);
	bool bClose = false;
	FVector CloseEye = FVector::ZeroVector, CloseLook = FVector::ZeroVector;
	float MinDistance = 2700.f;
	float FlightHeight = 0.f;

	switch (Sim.Phase)
	{
	case EFuryPhase::PlaySelect:
	case EFuryPhase::PatSelect:
		Include(Sim.BallSpot() + FVector2D(Sim.OffenseDir() * 300.f, 0.f), 1300.f);
		break;
	case EFuryPhase::Lineup:
	case EFuryPhase::PreSnap:
	case EFuryPhase::Break:
		if (Sim.PlayType == EFuryPlayType::Kickoff)
		{
			// The kicking team and the first stretch of field in front of it.
			for (int32 Slot = 0; Slot < TeamSize; ++Slot)
			{
				Include(Sim.Players[Sim.KickingTeam * TeamSize + Slot].Home, 150.f);
			}
			Include(FVector2D(Sim.LosX + Dir(Sim.KickingTeam) * 1200.f, 0.f), 100.f);
		}
		else
		{
			for (const FFurySimPlayer& P : Sim.Players)
			{
				// The deep safety (and a deep returner) can be left out of the pre-snap picture.
				if (FMath::Abs(P.Home.X - Sim.LosX) < 16.f * Yard)
				{
					Include(P.Home, 170.f);
				}
			}
		}
		break;
	case EFuryPhase::Live:
		if (Ball.State == EFuryBallState::Kick || Ball.State == EFuryBallState::FieldGoal || Ball.State == EFuryBallState::Pass)
		{
			// Frame a moving stretch of the flight path. Converting height into depth at the
			// sideline camera angle keeps the ball and the approaching catch point in view.
			const FVector2D LookAhead = (Ball.Land() - BallFlat).GetClampedToMaxSize(1250.f);
			FlightHeight = FMath::Max(0.f, static_cast<float>(Ball.Pos.Z)) * 0.48f;
			const float BallDepth = (Ball.Pos.Z - FlightHeight) * 1.48f;
			Include(BallFlat - FVector2D(0.f, BallDepth), 370.f);
			Include(BallFlat + LookAhead + FVector2D(0.f, FlightHeight * 1.48f), 560.f);
			MinDistance = 3200.f;
		}
		else if (Carrier != INDEX_NONE && Sim.IsPasser(Carrier))
		{
			// The pocket and everyone the quarterback could throw to.
			for (int32 Slot = 0; Slot < TeamSize; ++Slot)
			{
				const FFurySimPlayer& P = Sim.Players[Sim.Offense * TeamSize + Slot];
				Include(P.P + P.V * 0.25f, Slot >= 4 ? 260.f : 200.f);
			}
		}
		else if (Carrier != INDEX_NONE)
		{
			// A runner: him, the grass ahead of him, and the nearest men chasing.
			const FFurySimPlayer& C = Sim.Players[Carrier];
			Include(C.P, 520.f);
			Include(C.P + FVector2D(Dir(C.Team) * 700.f, 0.f) + C.V * 0.35f, 300.f);
			float Nearest[2] = { 1.e12f, 1.e12f };
			FVector2D Chasers[2] = { C.P, C.P };
			for (const FFurySimPlayer& P : Sim.Players)
			{
				if (P.Team == C.Team || P.bDown)
				{
					continue;
				}
				const float Dist = FVector2D::DistSquared(P.P, C.P);
				if (Dist < Nearest[0]) { Nearest[1] = Nearest[0]; Chasers[1] = Chasers[0]; Nearest[0] = Dist; Chasers[0] = P.P; }
				else if (Dist < Nearest[1]) { Nearest[1] = Dist; Chasers[1] = P.P; }
			}
			for (int32 i = 0; i < 2; ++i)
			{
				if (Nearest[i] < FMath::Square(18.f * Yard)) { Include(Chasers[i], 200.f); }
			}
		}
		else
		{
			Include(BallFlat, 800.f);
		}
		// Nobody should be playing blind: keep every human-controlled athlete near the play in shot.
		for (const FFurySeat& Seat : Sim.Seats)
		{
			if (Seat.bActive && Seat.Player != INDEX_NONE && FVector2D::DistSquared(Sim.Players[Seat.Player].P, BallFlat) < FMath::Square(30.f * Yard))
			{
				Include(Sim.Players[Seat.Player].P, 220.f);
			}
		}
		break;
	case EFuryPhase::Dead:
	case EFuryPhase::Celebrate:
		if (Sim.Phase == EFuryPhase::Celebrate && Sim.Scorer != INDEX_NONE && Sim.PhaseTime < 1.6f && !Options.Get(EFuryOption::ReducedMotion))
		{
			// Get in close on the celebration. The shot aims above his waist so he stands in the
			// lower half of the frame, clear of the banner.
			const FFurySimPlayer& S = Sim.Players[Sim.Scorer];
			const float Swing = Sim.PhaseTime * 0.45f;
			bClose = true;
			CloseLook = FVector(S.P.X, S.P.Y, 172.f);
			CloseEye = CloseLook + FVector(-Dir(S.Team) * FMath::Cos(Swing) * 740.f, 600.f + FMath::Sin(Swing) * 200.f, 40.f);
		}
		else
		{
			FVector2D Focus = Sim.WhistleFocus;
			const int32 Primary = Picker(0);
			if (Primary != INDEX_NONE && Sim.Seats[Primary].Player != INDEX_NONE)
			{
				Focus = Sim.Players[Sim.Seats[Primary].Player].P;
			}
			Include(Focus, 350.f);
			const bool bHumanView = Primary != INDEX_NONE;
			for (int32 i = 0; i < MaxSeats; ++i)
			{
				const FFurySeat& Seat = Sim.Seats[i];
				if (!Seat.bActive || Seat.Player == INDEX_NONE) { continue; }
				const FVector2D Pos = Sim.Players[Seat.Player].P;
				if ((bHumanView && !Seats[i].bBot) || FVector2D::DistSquared(Pos, Focus) < FMath::Square(10.f * Yard))
				{
					Include(Pos, 180.f);
				}
			}
			MinDistance = 1550.f;
		}
		break;
	case EFuryPhase::GameOver:
		Include(FVector2D(Ball.Pos.X * 0.5f, 0.f), 2200.f);
		break;
	}
	if (Min.X > Max.X)
	{
		Include(BallFlat, 1200.f);
	}

	// Turn the box into a shot. With a 32 degree lens tilted 34 degrees down, a camera at distance D
	// sees 0.287 D to either side, 0.378 D beyond its aim point and 0.233 D short of it.
	constexpr float Fov = 32.f, SinPitch = 0.559f, CosPitch = 0.829f;
	const FVector2D Centre = (Min + Max) * 0.5f;
	const FVector2D Half = (Max - Min) * 0.5f;
	const float Needed = FMath::Max(Half.X / 0.287f, (Half.Y + 190.f) / 0.3055f) * 1.06f;      // extra depth clears the score bug
	const float Distance = FMath::Clamp(Needed, MinDistance, 6200.f);
	const float AimY = Sim.AfterWhistle() ? Centre.Y : FMath::Clamp(Centre.Y + 0.0725f * Distance, -SidelineY, SidelineY + 300.f);
	const FVector2D Aim(FMath::Clamp(Centre.X, -EndLineX - 200.f, EndLineX + 200.f), AimY);

	FVector WantEye, WantLook;
	if (bClose)
	{
		WantEye = CloseEye;
		WantLook = CloseLook;
	}
	else
	{
		WantLook = FVector(Aim.X, Aim.Y, Sim.AfterWhistle() ? 105.f : FlightHeight);
		WantEye = WantLook + FVector(0.f, Distance * CosPitch, Distance * SinPitch);
	}

	// Cut rather than swoop when the shot changes completely (to and from the close-up, or a long way down the field).
	const bool bWasClose = CamEye.Z < 600.f;
	const bool bCut = bSnap || bWasClose != bClose || FMath::Abs(CamLook.X - WantLook.X) > 4500.f;
	if (bCut)
	{
		CamEye = WantEye;
		CamLook = WantLook;
	}
	else
	{
		// Pull back quickly when something needs to be seen; ease in gently so the picture does not pump.
		const bool bWidening = WantEye.Z > CamEye.Z;
		CamLook = Smooth(CamLook, WantLook, 4.2f, DeltaTime);
		CamEye.X = FMath::Lerp(CamEye.X, WantEye.X, 1.f - FMath::Exp(-4.2f * DeltaTime));
		const float ZoomRate = bWidening ? 3.4f : 1.3f;
		CamEye.Y = FMath::Lerp(CamEye.Y, WantEye.Y, 1.f - FMath::Exp(-ZoomRate * DeltaTime));
		CamEye.Z = FMath::Lerp(CamEye.Z, WantEye.Z, 1.f - FMath::Exp(-ZoomRate * DeltaTime));
	}
	CamFov = bClose ? 38.f : Fov;
	if (FlightHeight > 0.f)
	{
		// Keep a rising ball clear of the score display while the tracking shot catches up.
		// Correct the pitch by only the amount needed to bring it below the upper fifth.
		const FVector Forward = (CamLook - CamEye).GetSafeNormal();
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Forward).GetSafeNormal();
		const FVector Up = FVector::CrossProduct(Forward, Right);
		const FVector ToBall = Ball.Pos - CamEye;
		const float Depth = FVector::DotProduct(ToBall, Forward);
		if (Depth > 1.f)
		{
			const float Aspect = OutputSize.Y > 0 ? static_cast<float>(OutputSize.X) / OutputSize.Y : 16.f / 9.f;
			const float TopAngle = FMath::Atan(0.58f * FMath::Tan(FMath::DegreesToRadians(Fov * 0.5f)) / Aspect);
			const float Lift = FMath::Atan2(static_cast<float>(FVector::DotProduct(ToBall, Up)), Depth) - TopAngle;
			if (Lift > 0.f)
			{
				FRotator View = Forward.Rotation();
				View.Pitch += FMath::Min(14.f, FMath::RadiansToDegrees(Lift));
				CamLook = CamEye + View.Vector() * FVector::Distance(CamLook, CamEye);
			}
		}
	}

	FVector Jitter = FVector::ZeroVector;
	if (Options.Get(EFuryOption::ReducedMotion)) { Shake = 0.f; }
	if (Shake > 0.01f)
	{
		const float Time = GetWorld()->GetRealTimeSeconds();
		Jitter = FVector(FMath::Sin(Time * 61.f), FMath::Sin(Time * 47.f + 1.3f), FMath::Sin(Time * 53.f + 2.1f)) * Shake * 22.f;
		Shake = FMath::Max(0.f, Shake - DeltaTime * 1.9f);
	}
	SetCamera(CamEye + Jitter, CamLook + Jitter * 0.4f, CamFov);
}

void AFuryDirector::UpdateEffects(float DeltaTime)
{
	// Athletes on a team in Fury burn: flames lick off them as they move.
	for (int32 i = 0; i < NumPlayers && i < Athletes.Num(); ++i)
	{
		const FFurySimPlayer& P = Sim.Players[i];
		if (!Sim.Teams[P.Team].InFury() || Sim.Phase == EFuryPhase::PlaySelect)
		{
			continue;
		}
		// The ball carrier blazes; everyone else smoulders, more the faster they move.
		const float Rate = P.bHasBall ? 60.f : 5.f + 16.f * FMath::Min(1.f, static_cast<float>(P.V.Size()) / 700.f);
		const float Expected = FMath::Min(6.f, Rate * DeltaTime * Effects.ParticleDensity);
		int32 Flames = FMath::FloorToInt(Expected);
		if (Sparkle.FRand() < Expected - Flames) { ++Flames; }
		if (Flames > 0)
		{
			const FVector Chest = Athletes[i]->BoneWorld(AnimSet.Spine3 != INDEX_NONE ? AnimSet.Spine3 : 0).GetLocation();
			for (int32 j = 0; j < Flames; ++j)
			{
				Effects.Flame(Chest + FVector(0.f, 0.f, Sparkle.FRandRange(-60.f, 30.f)), FVector(P.V.X, P.V.Y, 0.f) * 0.25f);
			}
		}
	}

	// A long ball leaves a faint streak.
	if (Sim.Ball.State == EFuryBallState::Pass || Sim.Ball.State == EFuryBallState::Kick || Sim.Ball.State == EFuryBallState::FieldGoal)
	{
		const bool bFury = Sim.Ball.Thrower != INDEX_NONE && Sim.Teams[Sim.Players[Sim.Ball.Thrower].Team].InFury();
		const float Spacing = 40.f / Effects.ParticleDensity;
		const FVector Start = LastTrailPoint.Get(Sim.Ball.Pos);
		const FVector Segment = Sim.Ball.Pos - Start;
		const float Length = Segment.Size();
		// Space particles along the flight rather than adding one per displayed frame.
		if (Length > UE_SMALL_NUMBER && Length < 900.f)
		{
			float Distance = FMath::Max(0.f, Spacing - TrailDistance);
			for (; Distance <= Length; Distance += Spacing)
			{
				const FVector At = Start + Segment * (Distance / Length);
				Effects.Emit(At, FVector::ZeroVector, bFury ? FLinearColor(1.f, 0.4f, 0.05f) : FLinearColor(0.85f, 0.9f, 1.f), 0.22f, bFury ? 42.f : 20.f, bFury ? 2.2f : 0.7f, 0.f, 0.f, -60.f);
			}
			TrailDistance = Length + Spacing - Distance;
		}
		LastTrailPoint = Sim.Ball.Pos;
	}
	else
	{
		LastTrailPoint.Reset();
		TrailDistance = 0.f;
	}

	// Fireworks over the far stands after a score.
	if (FireworksLeft > 0)
	{
		FireworkTimer -= DeltaTime;
		if (FireworkTimer <= 0.f)
		{
			FireworkTimer = Sparkle.FRandRange(0.18f, 0.5f);
			--FireworksLeft;
			const FFuryTeam& Team = Sim.TeamInfo(FireworkTeam);
			const FLinearColor Colors[3] = { Team.Primary.GetLuminance() < 0.04f ? Team.Secondary : Team.Primary, Team.Secondary, FLinearColor(1.f, 0.85f, 0.4f) };
			const FVector Origin(Sparkle.FRandRange(-5500.f, 5500.f), Sparkle.FRandRange(-9000.f, -6500.f), Sparkle.FRandRange(4200.f, 6400.f));
			if (!Options.Get(EFuryOption::ReducedMotion)) { Effects.Firework(Origin, Colors[Sparkle.RandRange(0, 2)], Sparkle.FRandRange(1.f, 1.7f)); }
			Audio->PlayOneOf(TEXT("SFX_Fireworks"), 3, 0.55f, 0.1f);
		}
	}

	// Camera flashes twinkle in the crowd, more of them the louder it gets.
	if (!Options.Get(EFuryOption::ReducedMotion) && Stadium && Stadium->SeatSample().Num() > 0)
	{
		FlashTimer -= DeltaTime;
		const float PerSecond = FMath::Lerp(3.f, 110.f, FMath::Square(Excitement));
		while (FlashTimer <= 0.f)
		{
			FlashTimer += 1.f / PerSecond;
			const FVector Seat = Stadium->SeatSample()[Sparkle.RandRange(0, Stadium->SeatSample().Num() - 1)];
			Effects.Emit(Seat, FVector::ZeroVector, FLinearColor(0.9f, 0.95f, 1.f), 0.09f, 150.f, 5.f, 0.f, 0.f, 0.f);
		}
	}
}
