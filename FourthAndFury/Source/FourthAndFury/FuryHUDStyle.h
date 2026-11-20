#pragma once

#include "CoreMinimal.h"

/** Colours and button ids shared by the interface code. */
namespace FuryUI
{
	const FLinearColor Ink(0.012f, 0.014f, 0.02f);
	const FLinearColor Slate(0.045f, 0.05f, 0.065f);
	const FLinearColor White(1.f, 1.f, 1.f);
	const FLinearColor Dim(0.6f, 0.63f, 0.68f);
	const FLinearColor Blaze(1.f, 0.3f, 0.03f);     // the game's own orange
	const FLinearColor Gold(1.f, 0.76f, 0.07f);
	const FLinearColor Good(0.2f, 0.88f, 0.34f);
	const FLinearColor Bad(0.93f, 0.18f, 0.14f);

	enum EButton : uint8 { A, B, X, Y, LB, RB, Start, Stick, Turbo };
}
