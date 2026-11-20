#include "FuryHUD.h"

#include "FuryDirector.h"
#include "FuryHUDStyle.h"

using namespace FuryUI;

void AFuryHUD::DrawFieldGuide(AFuryDirector* Director)
{
	const int32 Seat = Director->PauseSeat;
	Panel(204.f, 105.f, 1512.f, 864.f, Blaze, 0.97f);
	Text(TEXT("FIELD GUIDE"), 256.f, 132.f, EFuryFace::BlackItalic, 80.f, White);
	Text(TEXT("Four downs to gain 30 yards. A full Fury meter gives your team three plays of unlimited turbo."), 258.f, 239.f, EFuryFace::SemiBold, 31.f, Dim);

	const TCHAR* Heads[] = {TEXT("WITH THE BALL"), TEXT("ON DEFENSE"), TEXT("AFTER THE WHISTLE")};
	const EButton Buttons[][4] = {{A, B, X, Y}, {A, B, X, Y}, {B, X, A, Turbo}};
	const TCHAR* Labels[][4] = {
		{TEXT("Spin past a tackle"), TEXT("Stiff-arm"), TEXT("Dive forward"), TEXT("Hurdle")},
		{TEXT("Switch defender"), TEXT("Big hit"), TEXT("Diving tackle"), TEXT("Jump to swat")},
		{TEXT("Shove an opponent"), TEXT("Dive or drop an elbow"), TEXT("Vote for the next play"), TEXT("Hold with shove for a big hit")}
	};
	for (int32 Column = 0; Column < 3; ++Column)
	{
		const float Left = 258.f + Column * 475.f;
		Rect(Left, 324.f, 438.f, 4.f, Blaze);
		Text(Heads[Column], Left, 343.f, EFuryFace::ExtraBoldItalic, 40.f, Gold);
		for (int32 Row = 0; Row < 4; ++Row)
		{
			const float Top = 424.f + Row * 80.f;
			const float W = Glyph(Seat, Buttons[Column][Row], Left, Top, 36.f);
			Text(Labels[Column][Row], Left + W + 12.f, Top - 1.f, EFuryFace::SemiBold, 29.f, White);
		}
	}
	Rect(258.f, 762.f, 1404.f, 2.f, Slate);
	Text(TEXT("At quarterback, press the button above a receiver to throw. Hold turbo while moving to sprint."), 258.f, 785.f, EFuryFace::Medium, 30.f, White);
	Prompts(Seat, {{B,TEXT("BACK")}, {Start,TEXT("RESUME")}}, 960.f, 892.f, 32.f);
}

void AFuryHUD::DrawSoloHints(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	if (Sim.Phase != EFuryPhase::Live || Sim.PlayCount > 3 || Sim.bKickMeterLive || Sim.bKickLocked) { return; }
	const FFurySeat& Seat = Sim.Seats[0];
	if (!Seat.bActive || Seat.Player == INDEX_NONE) { return; }
	const FFurySimPlayer& P = Sim.Players[Seat.Player];
	const bool bReturner = Sim.Ball.State == EFuryBallState::Kick && P.Job.Job == EFuryJob::Returner;
	Slant(548.f, 949.f, 824.f, 63.f, 15.f, Fade(Ink, 0.93f));
	if (Sim.IsPasser(Seat.Player))
	{
		Text(TEXT("PASS   /   PRESS THE BUTTON ABOVE A RECEIVER"), 960.f, 960.f, EFuryFace::Bold, 32.f, White, EFuryAlign::Center);
	}
	else if (P.bHasBall || bReturner)
	{
		Prompts(0, {{Stick, P.Team == 0 ? TEXT("RUN RIGHT") : TEXT("RUN LEFT")}, {Turbo,TEXT("SPRINT")}, {A,TEXT("SPIN")}}, 954.f, 965.f, 31.f);
	}
	else if (P.Team != Sim.BallTeam || Sim.Ball.State == EFuryBallState::Kick)
	{
		Prompts(0, {{A,TEXT("SWITCH")}, {B,TEXT("BIG HIT")}, {X,TEXT("DIVE TACKLE")}}, 960.f, 965.f, 31.f);
	}
	else
	{
		Prompts(0, {{Stick,TEXT("MOVE")}, {X,TEXT("JUMP FOR BALL")}, {B,TEXT("SHOVE")}}, 960.f, 965.f, 31.f);
	}
}
