#pragma once

#include "CoreMinimal.h"
#include "FurySim.h"

/**
 * A scripted stand-in for a person holding a controller.
 *
 * It looks at the match the way a player would and produces the same button presses and stick
 * movements, so the human control paths (calling plays, snapping, passing by icon, tackling,
 * switching defenders, kicking with the meter) can be exercised with no hardware attached -
 * in the headless balance test, in demo mode, and when filling seats with -FuryBots.
 */
class FFuryBot
{
public:
	void Reset(int32 InSeat, int32 Seed);
	FFurySeatInput Think(const FFurySim& Sim, float Dt);

private:
	int32 Seat = 0;
	FRandomStream Random;
	float Timer = 0.f;        // general-purpose wait before the next press
	float Hold = 0.f;         // how long the quarterback means to hold the ball
	float Weave = 0.f;
	bool bFreelance = false;  // this play the bot leaves its coverage to hunt the quarterback
	int32 WantCell = 4, WantPage = 0;
	bool bWantFlip = false;
	EFuryPhase LastPhase = EFuryPhase::GameOver;
	bool bPressedThisPhase = false;
};
