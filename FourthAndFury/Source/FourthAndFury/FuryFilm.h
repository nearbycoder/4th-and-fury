#pragma once

#include "CoreMinimal.h"
#include "FuryTypes.h"

class FFurySim;

struct FFuryFilmFrame
{
	float Time = 0.f;
	FVector2f Athlete[Fury::NumPlayers];
	FVector2f Ball;
	uint16 Down = 0;
	int8 Holder = INDEX_NONE;
};

struct FFuryPlayFilm
{
	struct FMoment { float Time; int32 Athlete; FName Action; };
	TArray<FFuryFilmFrame> Frames;
	TArray<FMoment> Moments;
	FString DownText, Result, ScoreLine, Clock;
	int32 Quarter = 0, Offense = 0;
	float Los = 0.f, ToGain = 0.f, Whistle = -1.f;
	bool bChains = false;
	uint8 Number[Fury::NumPlayers] = {};
	int8 Roster[Fury::NumPlayers] = {};

	bool Ready() const { return Frames.Num() >= 2 && Whistle >= 0.f; }
	float Duration() const { return Frames.IsEmpty() ? 0.f : Frames.Last().Time; }
	void Sample(const FFurySim& Sim, float Time, bool bForce = false);
};

/** Retains the last completed play while its successor is being recorded. */
struct FFuryFilmRecorder
{
	FFuryPlayFilm Last, Current, LongestTouchdown;
	int32 Play = INDEX_NONE;
	int32 BestYards = -1, BestTeam = INDEX_NONE;
	bool bWasLive = false, bWhistled = false, bKeepTouchdown = false;
	void Record(const FFurySim& Sim);
	void Reset();
};
