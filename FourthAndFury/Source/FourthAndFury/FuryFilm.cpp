#include "FuryFilm.h"

#include "FurySim.h"

void FFuryPlayFilm::Sample(const FFurySim& Sim, float Time, bool bForce)
{
	// The football simulation limits live plays to 30 s and the whistle window to 3 s.
	if (!Frames.IsEmpty() && (Time <= Frames.Last().Time || (!bForce && Time < Frames.Last().Time + 0.045f))) { return; }
	if (Frames.Num() >= 760) { return; }
	FFuryFilmFrame& Frame = Frames.AddDefaulted_GetRef();
	Frame.Time = Time;
	for (int32 i = 0; i < Fury::NumPlayers; ++i)
	{
		const FFurySimPlayer& P = Sim.Players[i];
		Frame.Athlete[i] = FVector2f(P.P);
		if (P.bDown) { Frame.Down |= 1u << i; }
	}
	const int32 Holder = Sim.CarrierIndex();
	Frame.Holder = Holder;
	Frame.Ball = Holder >= 0 ? Frame.Athlete[Holder] : FVector2f(Sim.Ball.Pos.X, Sim.Ball.Pos.Y);
}

void FFuryFilmRecorder::Reset()
{
	*this = FFuryFilmRecorder();
}

void FFuryFilmRecorder::Record(const FFurySim& Sim)
{
	// Kickoffs do not count as a scrimmage snap in the box score.
	const bool bStart = !bWasLive || Play != Sim.PlayCount;
	bWasLive = Sim.Phase == EFuryPhase::Live;
	if (bKeepTouchdown && (!Sim.AfterWhistle() || Play != Sim.PlayCount))
	{
		// Copy once after the late hits have finished. Later snaps can reuse their frame buffers.
		LongestTouchdown = Last;
		bKeepTouchdown = false;
	}
	if (Sim.Phase == EFuryPhase::Live)
	{
		if (bStart)
		{
			Play = Sim.PlayCount;
			bWhistled = false;
			Current.Frames.Reset();
			Current.Moments.Reset();
			Current.DownText = Sim.DownText();
			Current.Quarter = Sim.Quarter;
			Current.Offense = Sim.PlayType == EFuryPlayType::Kickoff ? Sim.KickingTeam : Sim.Offense;
			Current.Los = Sim.LosX;
			Current.ToGain = Sim.FirstDownX;
			Current.bChains = Sim.PlayType == EFuryPlayType::Scrimmage || Sim.PlayType == EFuryPlayType::Punt || Sim.PlayType == EFuryPlayType::FieldGoal;
			Current.Whistle = -1.f;
			for (int32 i = 0; i < Fury::NumPlayers; ++i)
			{
				Current.Number[i] = Sim.RosterOf(Sim.Players[i]).Number;
				Current.Roster[i] = Sim.Players[i].Roster;
			}
		}
		Current.Sample(Sim, Sim.LiveTime);
	}
	else if (Sim.AfterWhistle() && Play == Sim.PlayCount)
	{
		if (!bWhistled)
		{
			Current.Whistle = Sim.LiveTime;
			Current.Result = Sim.ResultTitle.IsEmpty() ? Sim.ResultDetail : Sim.ResultTitle;
			Current.ScoreLine = Sim.Phase == EFuryPhase::Celebrate ? Sim.ResultDetail : FString();
			Current.Clock = Sim.ClockText();
			Current.Sample(Sim, Sim.LiveTime, true);
			Swap(Current, Last);
			bWhistled = true;
		}
		Last.Sample(Sim, Sim.LiveTime + Sim.PhaseTime);
	}
	else { return; }
	FFuryPlayFilm& Film = bWhistled ? Last : Current;
	for (const FFuryEvent& E : Sim.Events)
	{
		const TCHAR* Label = nullptr;
		switch (E.Type)
		{
		case EFuryEvent::Throw: Label = TEXT("THROW"); break;
		case EFuryEvent::Catch: Label = TEXT("CATCH"); break;
		case EFuryEvent::Handoff: Label = TEXT("HANDOFF"); break;
		case EFuryEvent::Intercept: Label = TEXT("INTERCEPTION"); break;
		case EFuryEvent::BigHit: Label = TEXT("BIG HIT"); break;
		case EFuryEvent::Tackle: Label = TEXT("TACKLE"); break;
		case EFuryEvent::Fumble: Label = TEXT("FUMBLE"); break;
		case EFuryEvent::Recover: Label = TEXT("RECOVERY"); break;
		case EFuryEvent::LateHit: Label = TEXT("LATE HIT"); break;
		case EFuryEvent::Touchdown:
			Label = TEXT("TOUCHDOWN");
			if (FMath::RoundToInt(E.Value) > BestYards)
			{
				BestYards = FMath::RoundToInt(E.Value);
				BestTeam = E.Team;
				bKeepTouchdown = true;
			}
			break;
		case EFuryEvent::Kickoff: case EFuryEvent::PuntKick: case EFuryEvent::FieldGoalKick: Label = TEXT("KICK"); break;
		default: break;
		}
		if (Label && E.Player >= 0 && E.Player < Fury::NumPlayers && Film.Moments.Num() < 50)
		{
			Film.Moments.Add({ Sim.LiveTime + (bWhistled ? Sim.PhaseTime : 0.f), E.Player, FName(Label) });
		}
	}
}
