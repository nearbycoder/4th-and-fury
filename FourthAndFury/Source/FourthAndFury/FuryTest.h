#pragma once

#include "CoreMinimal.h"

namespace Fury
{
	/**
	 * Plays whole computer-vs-computer matches as fast as the machine allows and logs what happened:
	 * scores, play outcomes, event counts, and any game that hung. Run with -FurySimTest=<games>.
	 * Bots > 0 seats that many scripted "humans" (alternating sides), which exercises the same
	 * control paths a person with a controller uses.
	 */
	void RunSimTest(int32 Games, float Skill, int32 Bots, bool bVerbose);
}
