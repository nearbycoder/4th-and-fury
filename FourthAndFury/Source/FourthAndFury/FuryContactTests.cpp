#include "FurySim.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "FuryFilm.h"
#include "Misc/AutomationTest.h"

namespace
{
	using namespace Fury;
	constexpr float Dt = 1.f / 120.f;

	// Use real input and rules. Only starting positions, clock and ball ownership
	// are staged so these tests need neither a render nor a random play call.
	FFurySim Scrimmage()
	{
		FFurySim Sim;
		Sim.SetSeat(0, true, 0);
		Sim.SetSeat(1, true, 1);
		Sim.StartMatch(0, 1, 120.f, 0.5f, 38);
		Sim.Phase = EFuryPhase::Live;
		Sim.PhaseTime = Sim.LiveTime = 0.f;
		Sim.PlayType = EFuryPlayType::Scrimmage;
		Sim.Offense = Sim.BallTeam = 0;
		Sim.Down = 2;
		Sim.LosX = 0.f;
		Sim.FirstDownX = 30.f * Yard;
		for (int32 i = 0; i < NumPlayers; ++i)
		{
			FFurySimPlayer& P = Sim.Players[i];
			P = FFurySimPlayer();
			P.Team = i / TeamSize;
			P.Slot = i % TeamSize;
			P.P = FVector2D(-2500.f - i * 110.f, -1200.f);
			P.React = 60.f;
			P.Act = EFuryAct::Move;
		}
		for (int32 i = 0; i < 2; ++i)
		{
			const int32 Athlete = i * TeamSize;
			Sim.Seats[i].Player = Athlete;
			Sim.Players[Athlete].Seat = i;
		}
		Sim.Ball.State = EFuryBallState::Held;
		Sim.Ball.Holder = 0;
		Sim.Players[0].bHasBall = true;
		Sim.Events.Reset();
		return Sim;
	}

	bool HasEvent(const FFurySim& Sim, EFuryEvent Type, int32 Attacker)
	{
		return Sim.Events.ContainsByPredicate([=](const FFuryEvent& Event) { return Event.Type == Type && Event.Player == Attacker; });
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFurySwitchTest, "Fury.Football.OnePressOneDefender",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFurySwitchTest::RunTest(const FString&)
{
	FFurySim Sim = Scrimmage();
	Sim.Ball.Pos = FVector(Sim.Players[0].P, 110.f);
	const int32 Closest = TeamSize + 1;
	Sim.Players[Closest].P = Sim.Players[0].P + FVector2D(250.f, 0.f);
	FFurySeatInput Input[MaxSeats];
	Input[1].A = true;
	Sim.Step(Dt, Input);
	TestEqual(TEXT("Control stays on the nearest free defender"), Sim.Seats[1].Player, Closest);
	Sim = Scrimmage();
	Sim.Phase = EFuryPhase::PreSnap;
	Sim.PhaseTime = 0.4f;
	Sim.Step(Dt, Input);
	TestEqual(TEXT("Pre-snap cycle advances exactly one slot"), Sim.Seats[1].Player, TeamSize + 1);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryWhistleContactTest, "Fury.Football.WhistleContact",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FFuryWhistleContactTest::RunTest(const FString&)
{
	FFurySeatInput Input[MaxSeats];
	FFurySim Sim = Scrimmage();
	Sim.Players[0].P = FVector2D(570.f, SidelineY + 10.f);
	Sim.Step(Dt, Input);
	TestTrue(TEXT("Sideline whistle"), Sim.Phase == EFuryPhase::Dead);
	const FVector Spot = Sim.Ball.Pos;
	const float Clock = Sim.Clock;
	const FFuryTeamState Team = Sim.Teams[0];
	FFurySim Quiet = Sim;
	for (FFurySimPlayer& P : Sim.Players) { P.Think = 60.f; }
	FFurySimPlayer& Home = Sim.Players[0];
	FFurySimPlayer& Away = Sim.Players[TeamSize];
	Home.P = FVector2D(0, 0);
	Away.P = FVector2D(144, 0);
	Input[0].Stick.X = 1.f;
	Input[0].B = true;
	Sim.Step(Dt, Input);
	Input[0] = FFurySeatInput();
	TestFalse(TEXT("Wind-up is silent"), HasEvent(Sim, EFuryEvent::LateHit, 0));
	for (int32 i = 0; i < 25; ++i) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("Shove lands at the contact key"), Away.bDown && HasEvent(Sim, EFuryEvent::LateHit, 0));
	FFurySim Counter = Sim;
	for (int32 i = 0; i < 72; ++i) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("Runner is on the ground"), Away.Act == EFuryAct::Down);
	Home.P = Away.P - FVector2D(155, 0);
	Input[0].X = true;
	Sim.Step(Dt, Input);
	Input[0].X = false;
	TestTrue(TEXT("X selects a ground follow-up"), Home.Act == EFuryAct::ElbowDrop);
	FFurySim Miss = Sim;
	Miss.Players[TeamSize].P.Y += 300.f;
	Miss.Events.Reset();
	Sim.Events.Reset();
	for (int32 i = 0; i < 68; ++i) { Sim.Step(Dt, Input); Miss.Step(Dt, Input); }
	TestTrue(TEXT("Ground contact starts a prone reaction"), HasEvent(Sim, EFuryEvent::LateHit, 0) && Away.Act == EFuryAct::GroundRecoil);
	TestFalse(TEXT("A moved target takes no impact"), HasEvent(Miss, EFuryEvent::LateHit, 0));
	// On a separate branch the attacker stays upright after the shove.
	while (Counter.PhaseTime < 2.5f && Counter.AfterWhistle()) { Counter.Step(Dt, Input); }
	FFurySimPlayer& Defender = Counter.Players[TeamSize];
	TestTrue(TEXT("The shoved player can get back up before the whistle window closes"), Counter.AfterWhistle() && Defender.Free());
	Defender.P = Counter.Players[0].P - FVector2D(190.f, 0.f);
	Input[1].X = true;
	Input[1].Stick.X = 1.f;
	Counter.Step(Dt, Input);
	Input[1] = FFurySeatInput();
	for (int32 i = 0; i < 36; ++i) { Counter.Step(Dt, Input); }
	TestTrue(TEXT("Opposing seat can tackle back"), HasEvent(Counter, EFuryEvent::LateHit, TeamSize) && Counter.Players[0].bDown);
	TestTrue(TEXT("Late hits preserve spot, possession, clock and credited stats"),
		Counter.Ball.Pos == Spot && Counter.BallTeam == 0 && Counter.Clock == Clock && Counter.Teams[0].Score == Team.Score &&
		Counter.Teams[0].Fury == Team.Fury && Counter.Teams[0].RushYards == Team.RushYards && Counter.Seats[1].Tackles == 0);
	FFurySim Vote = Sim;
	Input[0].A = true;
	Vote.Step(Dt, Input);
	TestTrue(TEXT("One vote leaves both seats playing"), Vote.AfterWhistle());
	Input[0].A = false;
	Input[1].A = true;
	Vote.Step(Dt, Input);
	TestTrue(TEXT("Both votes advance"), Vote.Phase == EFuryPhase::PlaySelect);
	Input[1].A = false;
	while (Sim.PhaseTime < 2.99f && Sim.AfterWhistle()) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("The full window stays open"), Sim.AfterWhistle());
	for (int32 i = 0; i < 2; ++i) { Sim.Step(Dt, Input); }
	for (int32 i = 0; i < 361; ++i) { Quiet.Step(Dt, Input); }
	TestTrue(TEXT("The same next down and line follow a quiet or contested whistle"),
		Sim.Phase == EFuryPhase::PlaySelect && Sim.Down == Quiet.Down && Sim.LosX == Quiet.LosX &&
		Sim.BallY == Quiet.BallY && Sim.Offense == Quiet.Offense && Sim.Down == Vote.Down && Sim.LosX == Vote.LosX);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryLiveDiveTest, "Fury.Football.LiveDiveAndTouchdown",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FFuryLiveDiveTest::RunTest(const FString&)
{
	FFurySeatInput Input[MaxSeats];
	FFurySim Sim = Scrimmage();
	Sim.Players[0].P = FVector2D(200, 0);
	Sim.Players[TeamSize].P = FVector2D::ZeroVector;
	Sim.Teams[1].FuryPlays = 2; // deterministic tackle odds
	Input[1].Stick.X = 1.f;
	Input[1].X = true;
	Sim.Step(Dt, Input);
	Input[1] = FFurySeatInput();
	for (int32 i = 0; i < 45; ++i) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("A button dive can tackle the live carrier during its input cooldown"), Sim.Seats[1].Tackles == 1 && Sim.Players[0].bDown);

	Sim = Scrimmage();
	Sim.Clock = Dt / 2.f;
	Sim.Players[0].P = FVector2D(GoalX + 10.f, 0.f);
	Sim.Step(Dt, Input);
	TestTrue(TEXT("Touchdown starts the whistle at zero on the clock"), Sim.Phase == EFuryPhase::Celebrate && Sim.Teams[0].Score == 6 && Sim.Clock == 0.f);
	TestTrue(TEXT("Scoring from midfield credits the runner's 50-yard play"), Sim.Teams[0].LongestTD == 50 && Sim.Teams[0].LongestScorer == Sim.Players[0].Roster && Sim.Teams[0].LongestType == TEXT("RUN") && Sim.Seats[0].Touchdowns == 1);
	for (int32 i = 0; i < 359; ++i) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("Scorer can still move just before three seconds"), Sim.AfterWhistle() && Sim.Players[0].Free());
	for (int32 i = 0; i < 2; ++i) { Sim.Step(Dt, Input); }
	TestTrue(TEXT("Conversion follows exactly one touchdown"), Sim.Phase == EFuryPhase::PatSelect && Sim.Teams[0].Score == 6);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryReplayTest, "Fury.Football.PlayFilm",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryReplayTest::RunTest(const FString&)
{
	FFurySim Sim = Scrimmage();
	FFuryFilmRecorder Film;
	FFurySeatInput Input[MaxSeats];
	Film.Record(Sim);
	Sim.Players[0].P = FVector2D(400.f, 100.f);
	for (int32 i = 0; i < 12; ++i) { Sim.Step(Dt, Input); Film.Record(Sim); Sim.Events.Reset(); }
	TestFalse(TEXT("A live unfinished play cannot be replayed yet"), Film.Last.Ready());
	Sim.Players[0].P = FVector2D(GoalX + 12.f, 0.f);
	Sim.Step(Dt, Input);
	Film.Record(Sim);
	Sim.Events.Reset();
	TestTrue(TEXT("Whistled film contains snap, player samples and scoring event"), Film.Last.Ready() && Film.Last.Frames[0].Holder == 0 &&
		Film.Last.Moments.ContainsByPredicate([](const FFuryPlayFilm::FMoment& M) { return M.Athlete == 0 && M.Action == FName(TEXT("TOUCHDOWN")); }));
	for (int32 i = 0; i < 120; ++i) { Sim.Step(Dt, Input); Film.Record(Sim); Sim.Events.Reset(); }
	const float Length = Film.Last.Duration();
	TestTrue(TEXT("Film continues beyond the whistle"), Length >= Film.Last.Whistle + 0.9f);
	const int32 Count = Film.Last.Frames.Num();
	Sim.PlayType = EFuryPlayType::Kickoff; // a kick may share the preceding conversion's snap count
	Sim.Phase = EFuryPhase::Live;
	Sim.LiveTime = 0.f;
	Film.Record(Sim);
	TestTrue(TEXT("The next snap preserves the old film and its result"), Film.Last.Frames.Num() == Count && Film.Last.Result == TEXT("TOUCHDOWN!") && Film.Current.Whistle < 0.f);
	TestTrue(TEXT("The postgame scoring replay retains the entire whistle and scorer"), Film.LongestTouchdown.Ready() && Film.LongestTouchdown.Duration() == Length && Film.BestTeam == 0 && Film.BestYards == 50);
	Film.Reset();
	TestFalse(TEXT("A new match clears old film"), Film.Last.Ready());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryJerseyTest, "Fury.League.JerseyNumbers",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryJerseyTest::RunTest(const FString&)
{
	for (const FFuryTeam& Team : Fury::Teams())
	{
		TSet<int32> Used;
		for (const FFuryRosterEntry& Entry : Team.Roster)
		{
			TestTrue(Team.Name + TEXT(" has a unique, wearable number for ") + Entry.Name, Entry.Number > 0 && Entry.Number <= 99 && !Used.Contains(Entry.Number));
			Used.Add(Entry.Number);
		}
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryDurationTest, "Fury.Football.ThreeFuryPlays",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryDurationTest::RunTest(const FString&)
{
	FFurySeatInput Input[MaxSeats];
	FFurySim Sim = Scrimmage();
	Sim.Teams[0].Fury = 0.95f;
	Sim.Players[0].P = FVector2D(GoalX + 5.f, 0.f);
	Sim.Step(Dt, Input);
	TestEqual(TEXT("A scoring play ignites three plays"), Sim.Teams[0].FuryPlays, 3);
	while (Sim.AfterWhistle()) { Sim.Step(Dt, Input); }
	TestEqual(TEXT("The play that earned Fury does not spend a charge"), Sim.Teams[0].FuryPlays, 3);
	for (int32 Remaining = 3; Remaining > 0; --Remaining)
	{
		Sim.PlayType = EFuryPlayType::Scrimmage;
		Sim.Phase = EFuryPhase::PreSnap;
		Sim.PhaseTime = 2.f;
		Input[0].A = true;
		Sim.Step(Dt, Input);
		TestTrue(TEXT("A charged play reaches its live snap"), Sim.Phase == EFuryPhase::Live && Sim.Teams[0].FuryPlays == Remaining);
		Input[0].A = false;
		Sim.Ball.State = EFuryBallState::Held;
		Sim.Ball.Holder = 0;
		Sim.Players[0].bHasBall = true;
		Sim.Players[0].P = FVector2D(100.f, SidelineY + 20.f);
		Sim.Step(Dt, Input);
		while (Sim.AfterWhistle()) { Sim.Step(Dt, Input); }
		TestEqual(TEXT("A completed snap spends exactly one charge"), Sim.Teams[0].FuryPlays, Remaining - 1);
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryReturnTest, "Fury.Football.EndZoneReturns",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryReturnTest::RunTest(const FString&)
{
	FFurySim Sim = Scrimmage();
	FFurySeatInput Input[MaxSeats];
	const int32 Returner = TeamSize + 1;
	Sim.PlayType = EFuryPlayType::Kickoff;
	Sim.KickingTeam = 0;
	Sim.Players[0].bHasBall = false;
	// Deliver the ball to an uncontested receiver in the away end zone.
	Sim.Ball.State = EFuryBallState::Snap;
	Sim.Ball.Holder = INDEX_NONE;
	Sim.Ball.Target = Returner;
	Sim.Ball.Duration = 2.f * Dt;
	Sim.Players[Returner].P = FVector2D(GoalX + 2.f * Yard, 0.f);
	Sim.Step(Dt, Input);
	Sim.Step(Dt, Input);
	TestEqual(TEXT("Away returner gains possession"), Sim.CarrierIndex(), Returner);
	FFurySim Touchback = Sim;
	Touchback.Players[Returner].P.Y = SidelineY + 5.f;
	Touchback.Step(Dt, Input);
	TestTrue(TEXT("A return ending inside its own end zone is a touchback"), Touchback.ResultTitle == TEXT("TOUCHBACK") && Touchback.Teams[0].Score == 0);
	Sim.Players[Returner].P.X = GoalX - Yard;
	Sim.Step(Dt, Input);
	FFurySim Score = Sim;
	Score.Players[Returner].P.X = -GoalX - 5.f;
	Score.Step(Dt, Input);
	TestTrue(TEXT("A goal-to-goal return includes its two end-zone yards"), Score.Teams[1].LongestTD == 102 && Score.Teams[1].LongestType == TEXT("KICK RETURN"));
	Sim.Players[Returner].P = FVector2D(GoalX + Yard, SidelineY + 5.f);
	Sim.Step(Dt, Input);
	TestTrue(TEXT("Retreating into the end zone concedes two points to the kicking team"), Sim.ResultTitle == TEXT("SAFETY") && Sim.Teams[0].Score == 2 && Sim.Teams[1].Score == 0);
	return true;
}
#endif
