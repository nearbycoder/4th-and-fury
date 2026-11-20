#pragma once

#include "CoreMinimal.h"

DECLARE_LOG_CATEGORY_EXTERN(LogFury, Log, All);

/**
 * Shared constants and small types.
 *
 * Field space: X runs goal to goal (team 0 attacks +X, team 1 attacks -X), Y runs sideline to
 * sideline, Z is up, everything in Unreal units (cm). The broadcast camera sits on the +Y side.
 */
namespace Fury
{
	constexpr float Yard = 91.44f;
	constexpr float GoalX = 50.f * Yard;            // goal lines at x = +-GoalX
	constexpr float EndLineX = 60.f * Yard;         // backs of the end zones
	constexpr float SidelineY = 26.6667f * Yard;    // sidelines at y = +-SidelineY
	constexpr float HashY = 6.1f * 100.f;           // inbound hash rows

	constexpr int32 TeamSize = 7;
	constexpr int32 NumPlayers = TeamSize * 2;
	constexpr int32 MaxSeats = 8;                   // human players
	constexpr int32 MaxSeatsPerTeam = 4;

	/** +1 for the team attacking +X, -1 for the team attacking -X. */
	inline float Dir(int32 Team) { return Team == 0 ? 1.f : -1.f; }

	/** Yards from a team's own goal line to a world X (0 = own goal line, 100 = opponent's). */
	inline float YardLine(int32 Team, float X) { return (X * Dir(Team) + GoalX) / Yard; }
	inline float WorldX(int32 Team, float YardsFromOwnGoal) { return (YardsFromOwnGoal * Yard - GoalX) * Dir(Team); }

	inline float Approach(float Value, float Target, float Step)
	{
		return Value < Target ? FMath::Min(Value + Step, Target) : FMath::Max(Value - Step, Target);
	}

	inline FVector2D FromAngle(float Radians) { return FVector2D(FMath::Cos(Radians), FMath::Sin(Radians)); }
	inline float AngleOf(const FVector2D& V) { return FMath::Atan2(V.Y, V.X); }
	inline float AngleDelta(float From, float To) { return FMath::FindDeltaAngleRadians(From, To); }
}

/** Positions. The body build and the pre-snap stance follow from these. */
enum class EFuryPos : uint8 { QB, OL, WR, RB, DL, LB, CB, S, K };

enum class EFuryBuild : uint8 { Lean, Mid, Big };

inline EFuryBuild BuildFor(EFuryPos Pos)
{
	switch (Pos)
	{
	case EFuryPos::OL: case EFuryPos::DL: return EFuryBuild::Big;
	case EFuryPos::QB: case EFuryPos::RB: case EFuryPos::LB: return EFuryBuild::Mid;
	default: return EFuryBuild::Lean;
	}
}

/** What an athlete is doing, as far as animation is concerned. The simulation sets it. */
enum class EFuryAct : uint8
{
	Stand,        // variant: EFuryStance
	Move,         // free locomotion, driven by velocity
	Snap, CatchSnap, Throw, Handoff,
	Catch,        // variant 0 chest, 1 high
	Swat,
	Block,        // engaged with an opponent
	Dive,         // diving tackle
	Tackle, BigHit, Shove,
	Hit,          // variant: EFuryFall
	Down,         // variant 0 on the back, 1 face down
	GetUp,        // variant 0 from the back, 1 from the front
	Stumble, StiffArm, Spin,
	Juke,         // variant 0 left, 1 right
	Hurdle, DiveBall, Kick, Punt, PickUp,
	Celebrate,    // variant 0 spike, 1 dance, 2 flex
	Dejected, Signal, ElbowDrop, GroundRecoil,
};

enum class EFuryStance : uint8 { Idle, Ready, ThreePoint, Center, QB, QBSet };
enum class EFuryFall : uint8 { Back, Front, Flip, Spin };

/** Which socket carries the ball. */
enum class EFuryGrip : uint8 { None, Hand, Tuck };
