#include "FuryTest.h"

#include "FuryBot.h"
#include "FurySim.h"

namespace
{
	const TCHAR* EventName(EFuryEvent Type)
	{
		switch (Type)
		{
		case EFuryEvent::PlayStart: return TEXT("PlayStart"); case EFuryEvent::Snap: return TEXT("Snap"); case EFuryEvent::Hut: return TEXT("Hut");
		case EFuryEvent::Throw: return TEXT("Throw"); case EFuryEvent::Pitch: return TEXT("Pitch"); case EFuryEvent::Handoff: return TEXT("Handoff");
		case EFuryEvent::Catch: return TEXT("Catch"); case EFuryEvent::Drop: return TEXT("Drop"); case EFuryEvent::Incomplete: return TEXT("Incomplete");
		case EFuryEvent::Tip: return TEXT("Tip"); case EFuryEvent::Intercept: return TEXT("Intercept"); case EFuryEvent::Tackle: return TEXT("Tackle");
		case EFuryEvent::BigHit: return TEXT("BigHit"); case EFuryEvent::Sack: return TEXT("Sack"); case EFuryEvent::Fumble: return TEXT("Fumble");
		case EFuryEvent::Recover: return TEXT("Recover"); case EFuryEvent::BrokenTackle: return TEXT("BrokenTackle"); case EFuryEvent::StiffArm: return TEXT("StiffArm");
		case EFuryEvent::Spin: return TEXT("Spin"); case EFuryEvent::Juke: return TEXT("Juke"); case EFuryEvent::Hurdle: return TEXT("Hurdle");
		case EFuryEvent::Dive: return TEXT("Dive"); case EFuryEvent::DiveMiss: return TEXT("DiveMiss"); case EFuryEvent::Shove: return TEXT("Shove");
		case EFuryEvent::Pancake: return TEXT("Pancake"); case EFuryEvent::LateHit: return TEXT("LateHit"); case EFuryEvent::Touchdown: return TEXT("Touchdown");
		case EFuryEvent::FirstDown: return TEXT("FirstDown"); case EFuryEvent::TurnoverOnDowns: return TEXT("TurnoverOnDowns"); case EFuryEvent::Safety: return TEXT("Safety");
		case EFuryEvent::Touchback: return TEXT("Touchback"); case EFuryEvent::OutOfBounds: return TEXT("OutOfBounds"); case EFuryEvent::Whistle: return TEXT("Whistle");
		case EFuryEvent::Kickoff: return TEXT("Kickoff"); case EFuryEvent::PuntKick: return TEXT("PuntKick"); case EFuryEvent::FieldGoalKick: return TEXT("FieldGoalKick");
		case EFuryEvent::FieldGoalGood: return TEXT("FieldGoalGood"); case EFuryEvent::FieldGoalNoGood: return TEXT("FieldGoalNoGood");
		case EFuryEvent::ExtraPointGood: return TEXT("ExtraPointGood"); case EFuryEvent::ExtraPointNoGood: return TEXT("ExtraPointNoGood");
		case EFuryEvent::TwoPointGood: return TEXT("TwoPointGood"); case EFuryEvent::TwoPointNoGood: return TEXT("TwoPointNoGood"); case EFuryEvent::Doink: return TEXT("Doink");
		case EFuryEvent::FuryStart: return TEXT("FuryStart"); case EFuryEvent::FuryEnd: return TEXT("FuryEnd"); case EFuryEvent::PlayPicked: return TEXT("PlayPicked");
		case EFuryEvent::QuarterEnd: return TEXT("QuarterEnd"); case EFuryEvent::Halftime: return TEXT("Halftime"); case EFuryEvent::Overtime: return TEXT("Overtime");
		case EFuryEvent::GameOver: return TEXT("GameOver"); case EFuryEvent::TwoMinute: return TEXT("TwoMinute");
		}
		return TEXT("?");
	}
}

void Fury::RunSimTest(int32 Games, float Skill, int32 Bots, bool bVerbose)
{
	constexpr float Dt = 1.f / 60.f;
	constexpr int32 NumEvents = static_cast<int32>(EFuryEvent::TwoMinute) + 1;
	TArray<int64> Totals;
	Totals.SetNumZeroed(NumEvents);
	int64 Points = 0, Plays = 0, Attempts = 0, Completions = 0, PassYards = 0, RushYards = 0, Stuck = 0, Overtimes = 0, Ties = 0;
	double SimSeconds = 0.0, LongestPlay = 0.0;
	int32 HighScore = 0, LowScore = 999;
	TMap<FString, int32> Titles;
	FFurySeatInput Inputs[Fury::MaxSeats];

	// Per-play breakdown for plays from scrimmage.
	struct FPlayStats { int32 Calls = 0, Throws = 0, Catches = 0, Picks = 0, Sacks = 0, Scores = 0, Fumbles = 0; double Yards = 0, AirYards = 0, CatchYards = 0, ThrowTime = 0; };
	TMap<FString, FPlayStats> ByPlay, ByDefense;
	int64 KickReturns = 0, KickReturnScores = 0;
	int64 Tally[12] = {};
	double KickReturnYards = 0;

	for (int32 Game = 0; Game < Games; ++Game)
	{
		FFurySim Sim;
		FRandomStream Pick(1000 + Game);
		const int32 NumTeams = Fury::Teams().Num();
		const int32 Home = Pick.RandRange(0, NumTeams - 1);
		const int32 Away = (Home + 1 + Pick.RandRange(0, NumTeams - 2)) % NumTeams;
		FFuryBot Bot[Fury::MaxSeats];
		for (int32 i = 0; i < FMath::Min(Bots, Fury::MaxSeats); ++i)
		{
			Sim.SetSeat(i, true, i % 2);
			Bot[i].Reset(i, 500 + Game);
		}
		Sim.StartMatch(Home, Away, 120.f, Skill, 77 + Game * 13);

		int32 Steps = 0, AfterWhistleSteps = 0;
		float PlayStart = 0.f;
		FString PlayName, DefenseName;
		bool bScrimmagePlay = false, bReturnPlay = false, bCounted = false;
		float KickCatchX = 0.f;
		EFuryPhase LastPhase = Sim.Phase;
		bool bAborted = false;
		while (Sim.Phase != EFuryPhase::GameOver)
		{
			for (int32 i = 0; i < FMath::Min(Bots, Fury::MaxSeats); ++i)
			{
				Inputs[i] = Bot[i].Think(Sim, Dt);
			}
			if (Sim.AfterWhistle()) { ++AfterWhistleSteps; }
			Sim.Step(Dt, Inputs);
			++Steps;
			for (const FFuryEvent& Event : Sim.Events)
			{
				++Totals[static_cast<int32>(Event.Type)];
				if (Event.Type == EFuryEvent::Snap)
				{
					bScrimmagePlay = Sim.PlayType == EFuryPlayType::Scrimmage && Sim.OffensePlay();
					bCounted = false;
					if (bScrimmagePlay)
					{
						PlayName = Sim.OffensePlay()->Name;
						DefenseName = Sim.DefensePlay()->Name;
						++ByPlay.FindOrAdd(PlayName).Calls;
						++ByDefense.FindOrAdd(DefenseName).Calls;
					}
				}
				if (Event.Type == EFuryEvent::Kickoff) { bReturnPlay = true; bScrimmagePlay = false; KickCatchX = 0.f; }
				if (bReturnPlay && Event.Type == EFuryEvent::Catch) { KickCatchX = Event.Pos.X; }
				if (bReturnPlay && (Event.Type == EFuryEvent::Whistle || Event.Type == EFuryEvent::Touchdown))
				{
					++KickReturns;
					KickReturnYards += FMath::Abs(Sim.Ball.Pos.X - KickCatchX) / Fury::Yard;
					KickReturnScores += Event.Type == EFuryEvent::Touchdown ? 1 : 0;
					bReturnPlay = false;
				}
				if (bScrimmagePlay)
				{
					const bool bTouchdown = Event.Type == EFuryEvent::Touchdown && Event.Team == Sim.Offense;
					for (FPlayStats* Stats : { &ByPlay.FindOrAdd(PlayName), &ByDefense.FindOrAdd(DefenseName) })
					{
						switch (Event.Type)
						{
						case EFuryEvent::Throw: ++Stats->Throws; Stats->AirYards += Event.Value; Stats->ThrowTime += Sim.LiveTime; break;
						case EFuryEvent::Catch: ++Stats->Catches; Stats->CatchYards += Event.Value; break;
						case EFuryEvent::Intercept: ++Stats->Picks; break;
						case EFuryEvent::Sack: ++Stats->Sacks; break;
						case EFuryEvent::Fumble: ++Stats->Fumbles; break;
						case EFuryEvent::Touchdown: if (bTouchdown && !bCounted) { ++Stats->Scores; Stats->Yards += Event.Value; } break;
						case EFuryEvent::Whistle: if (!bCounted) { Stats->Yards += Sim.BallTeam == Sim.Offense ? Sim.PlayYards : 0.f; } break;
						default: break;
						}
					}
					bCounted |= bTouchdown || Event.Type == EFuryEvent::Whistle;
				}
				if (bVerbose && Game == 0)
				{
					UE_LOG(LogFury, Log, TEXT("SIMTEST   %6.1fs Q%d %s  %-16s team=%d player=%d value=%.1f | %s %s"), Steps * Dt, Sim.Quarter, *Sim.ClockText(),
						EventName(Event.Type), Event.Team, Event.Player, Event.Value, *Sim.DownText(), *Sim.SpotText());
				}
			}
			Sim.Events.Reset();
			if (Sim.Phase != LastPhase)
			{
				if (Sim.Phase == EFuryPhase::Live) { PlayStart = Steps * Dt; }
				if (LastPhase == EFuryPhase::Live)
				{
					LongestPlay = FMath::Max(LongestPlay, static_cast<double>(Steps * Dt - PlayStart));
					++Titles.FindOrAdd(Sim.ResultTitle.IsEmpty() ? FString(TEXT("(plain)")) : Sim.ResultTitle);
				}
				LastPhase = Sim.Phase;
			}

			// Sanity: nothing may go missing or hang.
			bool bBad = Sim.Ball.Pos.ContainsNaN() || Sim.PhaseTime > 90.f || Steps - AfterWhistleSteps > 60 * 60 * 40;
			for (const FFurySimPlayer& P : Sim.Players)
			{
				bBad |= !FMath::IsFinite(P.P.X) || !FMath::IsFinite(P.P.Y) || !FMath::IsFinite(P.Yaw);
			}
			if (bBad)
			{
				UE_LOG(LogFury, Error, TEXT("SIMTEST game %d ABORTED: phase=%d phaseTime=%.1f playType=%d ball=%d steps=%d %s %s"), Game, static_cast<int32>(Sim.Phase),
					Sim.PhaseTime, static_cast<int32>(Sim.PlayType), static_cast<int32>(Sim.Ball.State), Steps, *Sim.DownText(), *Sim.SpotText());
				++Stuck;
				bAborted = true;
				break;
			}
		}
		if (bAborted)
		{
			continue;
		}
		for (int32 i = 0; i < 12; ++i) { Tally[i] += Sim.Tally[i]; }
		const int32 A = Sim.Teams[0].Score, B = Sim.Teams[1].Score;
		Points += A + B;
		HighScore = FMath::Max3(HighScore, A, B);
		LowScore = FMath::Min3(LowScore, A, B);
		Plays += Sim.PlayCount;
		SimSeconds += Steps * Dt;
		Overtimes += Sim.bOvertime ? 1 : 0;
		Ties += A == B ? 1 : 0;
		for (int32 Team = 0; Team < 2; ++Team)
		{
			Attempts += Sim.Teams[Team].Attempts;
			Completions += Sim.Teams[Team].Completions;
			PassYards += Sim.Teams[Team].PassYards;
			RushYards += Sim.Teams[Team].RushYards;
		}
		if (bVerbose || Game < 12)
		{
			UE_LOG(LogFury, Log, TEXT("SIMTEST game %2d: %s %d - %d %s%s  plays=%d  simtime=%.0fs"), Game, *Sim.TeamInfo(0).Name, A, B, *Sim.TeamInfo(1).Name,
				Sim.bOvertime ? TEXT(" (OT)") : TEXT(""), Sim.PlayCount, Steps * Dt);
		}
	}

	const float G = FMath::Max(1, Games - static_cast<int32>(Stuck));
	UE_LOG(LogFury, Log, TEXT("SIMTEST ===== %d games (skill %.2f, %d scripted humans), %lld aborted ====="), Games, Skill, Bots, Stuck);
	UE_LOG(LogFury, Log, TEXT("SIMTEST points/team/game %.1f  (low %d, high %d)  plays/game %.1f  minutes/game %.1f  longest play %.1fs  overtime %lld  ties %lld"),
		Points / (2.f * G), LowScore, HighScore, Plays / G, SimSeconds / G / 60.0, LongestPlay, Overtimes, Ties);
	UE_LOG(LogFury, Log, TEXT("SIMTEST passing %lld/%lld (%.0f%%)  %.1f yds/attempt  pass yds/team/game %.0f  rush yds/team/game %.0f"), Completions, Attempts,
		Attempts > 0 ? 100.f * Completions / Attempts : 0.f, Attempts > 0 ? static_cast<float>(PassYards) / Attempts : 0.f, PassYards / (2.f * G), RushYards / (2.f * G));
	for (int32 i = 0; i < NumEvents; ++i)
	{
		if (Totals[i] > 0)
		{
			UE_LOG(LogFury, Log, TEXT("SIMTEST   %-16s %7lld  (%.2f per game)"), EventName(static_cast<EFuryEvent>(i)), Totals[i], Totals[i] / G);
		}
	}
	UE_LOG(LogFury, Log, TEXT("SIMTEST catch contests: open %lld | contested %lld (picks %lld) | defender alone at catch %lld (picks %lld) | defender in lane %lld (picks %lld) | on tipped balls %lld"),
		Tally[0], Tally[1], Tally[4], Tally[2], Tally[5], Tally[3], Tally[6], Tally[7]);
	UE_LOG(LogFury, Log, TEXT("SIMTEST kick returns %lld  avg %.1f yds  touchdowns %lld"), KickReturns, KickReturns > 0 ? KickReturnYards / KickReturns : 0.0, KickReturnScores);
	for (int32 Pass = 0; Pass < 2; ++Pass)
	{
		UE_LOG(LogFury, Log, TEXT("SIMTEST   %-16s calls  yds/play  TD%%   throw%%  comp%%  air   catchAt  throwT  pick%%  sack%%  fum%%"), Pass == 0 ? TEXT("OFFENSE") : TEXT("DEFENSE"));
		for (const auto& Pair : Pass == 0 ? ByPlay : ByDefense)
		{
			const FPlayStats& St = Pair.Value;
			const float C = FMath::Max(St.Calls, 1), T = FMath::Max(St.Throws, 1), K = FMath::Max(St.Catches, 1);
			UE_LOG(LogFury, Log, TEXT("SIMTEST   %-16s %5d  %7.1f  %4.0f  %5.0f  %5.0f  %5.1f  %6.1f  %6.2f  %5.1f  %5.1f  %4.1f"), *Pair.Key, St.Calls, St.Yards / C, 100.f * St.Scores / C,
				100.f * St.Throws / C, 100.f * St.Catches / T, St.AirYards / T, St.CatchYards / K, St.ThrowTime / T, 100.f * St.Picks / T, 100.f * St.Sacks / C, 100.f * St.Fumbles / C);
		}
	}
	Titles.ValueSort([](int32 A, int32 B) { return A > B; });
	for (const auto& Pair : Titles)
	{
		UE_LOG(LogFury, Log, TEXT("SIMTEST   result %-18s %6d"), *Pair.Key, Pair.Value);
	}
}
