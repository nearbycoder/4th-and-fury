#pragma once

#include "CoreMinimal.h"

/**
 * Plays are data. Everything is in yards in "play space": X is downfield from the ball (the
 * offense attacks +X, so the defense lines up at positive X) and Y is toward the offense's right.
 * The simulation maps play space onto the field for whichever way the offense is heading.
 *
 * Offense slots: 0 QB, 1 C, 2 LG, 3 RG, 4 WR (split left), 5 WR (split right), 6 RB / slot.
 * Defense slots: 0 DE, 1 DT, 2 DE, 3 LB, 4 CB (on slot 4), 5 CB (on slot 5), 6 S.
 */
enum class EFuryJob : uint8
{
	None,
	// Offense
	Passer,       // drop back (optionally rolling out along Path) and throw
	PassBlock,
	RunBlock,
	Route,        // run Path, then work to open grass
	Carry,        // take the ball from the QB at Path[0], then run the rest of Path
	Keeper,       // quarterback keeps the ball and runs Path
	// Defense
	Rush,
	Blitz,        // rush after Delay seconds
	Man,          // cover offensive slot Target, lining up Cushion yards off him
	Zone,         // guard the circle (Zone, Radius), break on the ball
	Spy,          // mirror the quarterback, attack if he runs
	// Kicking game
	Kicker, Punter, Holder, Cover, Returner, ReturnBlock,
};

struct FFuryJobSpec
{
	EFuryJob Job = EFuryJob::None;
	TArray<FVector2D> Path;       // waypoints relative to the player's own lineup spot
	bool bInward = false;         // Path Y means "toward the middle of the formation" (split receivers)
	int32 Target = INDEX_NONE;
	float Delay = 0.f;
	float Cushion = 5.f;
	bool bPress = false;          // Man: jam the receiver at the snap
	FVector2D Zone = FVector2D::ZeroVector;
	float Radius = 8.f;
};

enum class EFuryPlayKind : uint8 { Pass, Run, Punt, FieldGoal };

struct FFuryOffPlay
{
	FString Name, Tagline;
	EFuryPlayKind Kind = EFuryPlayKind::Pass;
	FVector2D Spot[7];
	FFuryJobSpec Job[7];
	float Drop = 3.f;             // how far the passer drops from his spot
	int32 Primary = 4;            // first read for a computer quarterback
	bool bPlayAction = false;     // fake hand-off that freezes linebackers and safeties
	bool bScreen = false;         // linemen release downfield after a beat
};

struct FFuryDefPlay
{
	FString Name, Tagline;
	FVector2D Spot[7];
	FFuryJobSpec Job[7];
};

namespace FuryPlaybook
{
	const TArray<FFuryOffPlay>& Offense();
	const TArray<FFuryDefPlay>& Defense();
	const FFuryOffPlay& Punt();
	const FFuryOffPlay& FieldGoal();
	const FFuryDefPlay& KickBlock();      // what a defense lines up in against a punt or field goal

	/** Mirror image of a play (left and right swapped). */
	FFuryOffPlay Flip(const FFuryOffPlay& Play);
	FFuryDefPlay Flip(const FFuryDefPlay& Play);

	constexpr int32 PlaysPerPage = 9;
}
