#include "FuryHUD.h"

#include "Engine/Canvas.h"
#include "Engine/TextureRenderTarget2D.h"
#include "FuryAthlete.h"
#include "FuryDirector.h"
#include "FuryHUDStyle.h"
#include "FuryInput.h"
#include "FuryPlaybook.h"
#include "FuryStadium.h"
#include "Kismet/KismetRenderingLibrary.h"

// Everything drawn over a match: the score bug, play calling, banners, tags over the athletes.

using namespace FuryUI;

namespace
{
	const TCHAR* QuarterName(int32 Quarter)
	{
		switch (Quarter)
		{
		case 1: return TEXT("1ST");
		case 2: return TEXT("2ND");
		case 3: return TEXT("3RD");
		case 4: return TEXT("4TH");
		default: return TEXT("OT");
		}
	}

	/** A team colour that still reads as a colour on a dark panel. */
	FLinearColor Bright(const FFuryTeam& Team)
	{
		return Team.Primary.GetLuminance() < 0.035f ? Team.Secondary : Team.Primary;
	}
}

void AFuryHUD::DrawMatch(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	DrawFieldTags(Director);
	if (Sim.Phase == EFuryPhase::PlaySelect)
	{
		DrawPlaySelect(Director);
	}
	else if (Sim.Phase == EFuryPhase::PatSelect)
	{
		DrawPatSelect(Director);
	}
	DrawScorebug(Director);
	DrawTurbo(Director);
	DrawKickMeter(Director);
	DrawResult(Director);
	if (Director->bQuickMatch && !Director->bPaused) { DrawSoloHints(Director); }
	DrawBanner(Director);

	if (Director->bDemo)
	{
		const float Pulse = 0.6f + 0.4f * FMath::Sin(Now() * 4.f);
		if (UTexture* Small = Director->UiTexture(TEXT("T_TitleSmall")))
		{
			Image(Small, 40.f, 940.f, 440.f, 110.f, FLinearColor(1.f, 1.f, 1.f, 0.9f));
		}
		Slant(1250.f, 962.f, 620.f, 70.f, 20.f, Fade(Ink, 0.8f));
		Text(TEXT("DEMO  -  PRESS"), 1290.f, 972.f, EFuryFace::BlackItalic, 40.f, Fade(White, Pulse));
		Glyph(INDEX_NONE, FuryUI::A, 1556.f, 974.f, 44.f);
		Text(TEXT("TO PLAY"), 1614.f, 972.f, EFuryFace::BlackItalic, 40.f, Fade(White, Pulse));
	}
	if (Director->bPaused)
	{
		DrawPause(Director);
	}

	// The stadium's video board gets redrawn a few times a second.
	BoardTimer -= GetWorld()->GetDeltaSeconds();
	if (BoardTimer <= 0.f)
	{
		BoardTimer = 0.25f;
		DrawBoard(Director);
	}
}

// ---------------------------------------------------------------------------------------------
// Score bug
// ---------------------------------------------------------------------------------------------

void AFuryHUD::DrawScorebug(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	const float Y = 22.f, H = 82.f, TeamW = 380.f, MidW = 210.f;
	const float X0 = 960.f - MidW * 0.5f - TeamW - 8.f;
	const float Time = Now();

	for (int32 Team = 0; Team < 2; ++Team)
	{
		const FFuryTeam& Info = Sim.TeamInfo(Team);
		const FFuryTeamState& St = Sim.Teams[Team];
		const float X = Team == 0 ? X0 : 960.f + MidW * 0.5f + 8.f;
		const FLinearColor Base = Info.Primary;
		const FLinearColor Deep(Base.R * 0.55f, Base.G * 0.55f, Base.B * 0.55f);
		SlantGradient(X, Y, TeamW, H, 22.f, Base, Deep);
		Slant(Team == 0 ? X : X + TeamW - 12.f, Y, 12.f, H, 22.f, Info.Secondary);
		const FLinearColor Ink2 = InkOn(Base);

		// Emblem, name, score: mirrored for the right-hand team.
		const float LogoX = Team == 0 ? X + 30.f : X + TeamW - 104.f;
		if (UTexture* Logo = Director->TeamLogo(St.League))
		{
			Image(Logo, LogoX, Y + 4.f, 74.f, 74.f);
		}
		const float NameX = Team == 0 ? X + 114.f : X + TeamW - 122.f;
		Text(Info.Abbr, NameX, Y + 12.f, EFuryFace::BlackItalic, 54.f, Ink2, Team == 0 ? EFuryAlign::Left : EFuryAlign::Right);
		const float ScoreX = Team == 0 ? X + TeamW - 22.f : X + 40.f;
		TextShadow(FString::FromInt(St.Score), ScoreX, Y + 2.f, EFuryFace::BlackItalic, 74.f, Ink2 == Ink ? Ink : White, Team == 0 ? EFuryAlign::Right : EFuryAlign::Left, 0, Ink2 == Ink ? 0.f : 3.f);

		// Point downfield inside the team block, above the Fury gauge. BallTeam follows
		// catches, recoveries and interceptions before the next down is set.
		if (Sim.Phase != EFuryPhase::GameOver && Sim.BallTeam == Team)
		{
			const float PX = Team == 0 ? X + TeamW - 106.f : X + 128.f;
			const float DX = Team == 0 ? 1.f : -1.f;
			Triangle(FVector2D(PX, Y + 32.f), FVector2D(PX, Y + 54.f), FVector2D(PX + DX * 14.f, Y + 43.f), Ink2);
		}

		// Fury meter under the team block.
		const float MX = Team == 0 ? X + 6.f : X + TeamW - 246.f;
		const bool bFury = St.InFury();
		const float Glow = bFury ? 0.75f + 0.25f * FMath::Sin(Time * 14.f) : 1.f;
		Meter(MX, Y + H + 8.f, 240.f, 14.f, St.Fury, bFury ? FLinearColor(1.f, 0.55f * Glow, 0.05f) : Fade(Blaze, 0.9f), Fade(Ink, 0.75f));
		if (UTexture* Flame = Director->UiTexture(TEXT("T_Icon_Flame")))
		{
			const float FX = Team == 0 ? MX + 250.f : MX - 34.f;
			Image(Flame, FX, Y + H + 1.f, 28.f, 28.f, bFury ? FLinearColor(1.f, 0.7f * Glow, 0.1f) : Fade(Dim, 0.6f));
		}
		if (bFury)
		{
			const float LabelX = Team == 0 ? MX + 290.f : MX - 46.f;
			TextShadow(FString::Printf(TEXT("FURY x%d"), St.FuryPlays), LabelX, Y + H + 2.f, EFuryFace::BlackItalic, 28.f, FLinearColor(1.f, 0.6f, 0.1f), Team == 0 ? EFuryAlign::Left : EFuryAlign::Right);
		}
	}

	// Clock.
	const float MX = 960.f - MidW * 0.5f;
	SlantGradient(MX, Y, MidW, H, 22.f, Fade(Slate, 0.96f), Fade(Ink, 0.96f));
	Text(Sim.bOvertime ? TEXT("SUDDEN DEATH") : QuarterName(Sim.Quarter), 960.f + 11.f, Y + 6.f, EFuryFace::Bold, Sim.bOvertime ? 20.f : 24.f, Gold, EFuryAlign::Center, 160);
	const bool bLate = Sim.Quarter >= 4 && Sim.Clock < 30.f && !Sim.bOvertime;
	Text(Sim.bOvertime ? FString(TEXT("--:--")) : Sim.ClockText(), 960.f + 9.f, Y + 24.f, EFuryFace::BlackItalic, 56.f, bLate ? FLinearColor(1.f, 0.35f + 0.3f * FMath::Sin(Time * 8.f), 0.2f) : White, EFuryAlign::Center);

	// Down and distance.
	if (Sim.Phase != EFuryPhase::GameOver && Sim.Phase != EFuryPhase::Celebrate)
	{
		const FString Down = Sim.DownText();
		const bool bShowSpot = Sim.PlayType == EFuryPlayType::Scrimmage || Sim.PlayType == EFuryPlayType::Punt || Sim.PlayType == EFuryPlayType::FieldGoal;
		const FString Spot = bShowSpot ? Sim.SpotText() : FString();
		const float DW = Measure(Down, EFuryFace::BlackItalic, 34.f).X;
		const float SW = Spot.IsEmpty() ? 0.f : Measure(Spot, EFuryFace::SemiBold, 28.f, 80).X + 34.f;
		const float W = DW + SW + 56.f;
		Slant(960.f - W * 0.5f, Y + H + 8.f, W, 46.f, 14.f, Fade(Ink, 0.88f));
		Text(Down, 960.f - W * 0.5f + 34.f, Y + H + 11.f, EFuryFace::BlackItalic, 34.f, Sim.Down == 4 && bShowSpot ? Gold : White);
		if (!Spot.IsEmpty())
		{
			Rect(960.f - W * 0.5f + 46.f + DW, Y + H + 18.f, 2.f, 26.f, Fade(White, 0.25f));
			Text(Spot, 960.f - W * 0.5f + 62.f + DW, Y + H + 15.f, EFuryFace::SemiBold, 28.f, Dim, EFuryAlign::Left, 80);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Banners and small readouts
// ---------------------------------------------------------------------------------------------

void AFuryHUD::DrawBanner(AFuryDirector* Director)
{
	const FFuryBanner& B = Director->Banner;
	const float Age = Now() - B.Start;
	if (Age < 0.f || Age > B.Length || B.Title.IsEmpty())
	{
		return;
	}
	// Whip in from the left, hold, whip out to the right.
	const float In = Ease(Age / 0.22f);
	const float Out = Ease((Age - (B.Length - 0.25f)) / 0.25f);
	const float Slide = Director->Options.Get(EFuryOption::ReducedMotion) ? 0.f : (1.f - In) * -900.f + Out * 1100.f;
	const float Alpha = FMath::Clamp(In * (1.f - Out), 0.f, 1.f);
	const float TitleSize = B.bBig ? 118.f : 62.f;
	const float BandH = B.bBig ? 150.f : 84.f;
	const float Y = B.bBig ? 250.f : 210.f;
	const float TitleW = Measure(B.Title, EFuryFace::BlackItalic, TitleSize).X;
	const float W = FMath::Max(TitleW + 220.f, B.bBig ? 900.f : 560.f);
	const float X = 960.f - W * 0.5f + Slide;
	const float Lean = BandH * 0.32f;
	const FLinearColor Deep(B.Color.R * 0.5f, B.Color.G * 0.5f, B.Color.B * 0.5f);

	Slant(X - 26.f, Y + 12.f, W + 52.f, BandH, Lean, Fade(Ink, 0.85f * Alpha));
	SlantGradient(X, Y, W, BandH, Lean, Fade(B.Color, Alpha), Fade(Deep, Alpha));
	// A bright streak that sweeps across once.
	const float Sweep = FMath::Clamp(Age / 0.5f, 0.f, 1.f);
	if (Sweep < 1.f)
	{
		Slant(X + W * Sweep - 40.f, Y, 80.f, BandH, Lean, Fade(White, 0.5f * (1.f - Sweep)));
	}
	const FLinearColor TextColor = InkOn(B.Color);
	const float Pop = B.bBig ? 1.f + 0.06f * FMath::Max(0.f, 1.f - Age / 0.3f) : 1.f;
	if (TextColor == Ink)
	{
		Text(B.Title, 960.f + Slide + Lean * 0.5f, Y + (BandH - TitleSize * Pop * 1.16f) * 0.5f, EFuryFace::BlackItalic, TitleSize * Pop, Fade(Ink, Alpha), EFuryAlign::Center);
	}
	else
	{
		TextShadow(B.Title, 960.f + Slide + Lean * 0.5f, Y + (BandH - TitleSize * Pop * 1.16f) * 0.5f, EFuryFace::BlackItalic, TitleSize * Pop, Fade(White, Alpha), EFuryAlign::Center, 0, B.bBig ? 6.f : 3.f);
	}
	if (!B.Detail.IsEmpty())
	{
		const float DetailSize = B.bBig ? 40.f : 28.f;
		const float DW = Measure(B.Detail, EFuryFace::Bold, DetailSize, 200).X + 80.f;
		Slant(960.f - DW * 0.5f + Slide * 1.15f, Y + BandH + 8.f, DW, DetailSize + 22.f, 14.f, Fade(Ink, 0.9f * Alpha));
		Text(B.Detail, 960.f + Slide * 1.15f + 7.f, Y + BandH + 14.f, EFuryFace::Bold, DetailSize, Fade(White, Alpha), EFuryAlign::Center, 200);
	}
}

void AFuryHUD::DrawResult(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	const float Time = Now();

	// How the last play went, once the whistle has gone.
	if (Sim.Phase == EFuryPhase::Dead && !Sim.ResultDetail.IsEmpty() && Sim.PhaseTime > 0.35f && Sim.PhaseTime < 2.4f
		&& !(Director->Banner.Detail == Sim.ResultDetail && Now() - Director->Banner.Start < Director->Banner.Length))
	{
		const float In = Ease((Sim.PhaseTime - 0.35f) / 0.25f);
		const float W = Measure(Sim.ResultDetail, EFuryFace::BlackItalic, 44.f).X + 90.f;
		Slant(960.f - W * 0.5f, 814.f + 12.f * (1.f - In), W, 64.f, 20.f, Fade(Ink, 0.86f * In));
		Text(Sim.ResultDetail, 960.f + 10.f, 820.f + 12.f * (1.f - In), EFuryFace::BlackItalic, 44.f, Fade(Sim.PlayYards < -0.5f ? FLinearColor(1.f, 0.45f, 0.35f) : White, In), EFuryAlign::Center);
	}

	if (Sim.AfterWhistle())
	{
		const int32 Seconds = FMath::CeilToInt(Sim.AfterWhistleSeconds - Sim.PhaseTime);
		const FString Label = FString::Printf(TEXT("LATE HITS   %02d"), Seconds);
		const float Y = 898.f;
		Slant(800.f, Y, 320.f, 44.f, 14.f, Fade(Ink, 0.9f));
		Text(Label, 965.f, Y + 3.f, EFuryFace::BlackItalic, 32.f, Gold, EFuryAlign::Center);
		if (!Director->bDemo)
		{
			int32 Joined = 0, Ready = 0;
			for (int32 i = 0; i < Fury::MaxSeats; ++i)
			{
				if (!Sim.Seats[i].bActive) { continue; }
				++Joined;
				if (Sim.ReadySeats & (1u << i)) { ++Ready; }
			}
			const FString Next = Joined > 1 ? FString::Printf(TEXT("NEXT PLAY  %d/%d"), Ready, Joined) : TEXT("NEXT PLAY");
			Slant(575.f, 958.f, 770.f, 58.f, 15.f, Fade(Ink, 0.85f));
			Prompts(Director->Picker(0), { { FuryUI::B, TEXT("SHOVE") }, { FuryUI::X, TEXT("DIVE / ELBOW") }, { FuryUI::A, *Next } }, 970.f, 971.f, 32.f);
		}
	}

	// The prompt to snap (or kick), aimed at whoever is calling the shots.
	if (Sim.Phase == EFuryPhase::PreSnap && Sim.PhaseTime > 0.3f)
	{
		const int32 Team = Sim.PlayType == EFuryPlayType::Kickoff ? Sim.KickingTeam : Sim.Offense;
		const int32 Seat = Sim.Captain(Team);
		if (Seat != INDEX_NONE)
		{
			const TCHAR* Verb = Sim.PlayType == EFuryPlayType::Kickoff ? TEXT("KICK OFF") : Sim.PlayType == EFuryPlayType::Punt ? TEXT("SNAP AND PUNT")
				: (Sim.PlayType == EFuryPlayType::FieldGoal || Sim.PlayType == EFuryPlayType::ExtraPoint) ? TEXT("SNAP IT") : TEXT("HIKE!");
			const float Pulse = 0.75f + 0.25f * FMath::Sin(Time * 7.f);
			const bool bRoutes = (Sim.PlayType == EFuryPlayType::Scrimmage || Sim.PlayType == EFuryPlayType::TwoPoint)
				&& !Sim.Teams[Sim.Defense()].bHuman && Sim.OffensePlay();
			const float W = Measure(Verb, EFuryFace::BlackItalic, 44.f).X + 230.f + (bRoutes ? 260.f : 0.f);
			Slant(960.f - W * 0.5f, 940.f, W, 66.f, 20.f, Fade(Ink, 0.86f));
			float X = 960.f - W * 0.5f + 40.f;
			X += SeatChip(Seat, X, 952.f, 42.f) + 12.f;
			X += Glyph(Seat, FuryUI::A, X, 950.f, 46.f) + 14.f;
			X += Text(Verb, X, 946.f, EFuryFace::BlackItalic, 44.f, Fade(White, Pulse));
			if (bRoutes)
			{
				X += 34.f;
				X += Glyph(Seat, FuryUI::LB, X, 956.f, 34.f) + 10.f;
				Text(TEXT("HOLD FOR ROUTES"), X, 958.f, EFuryFace::Bold, 26.f, Dim);
			}
		}
	}
}

void AFuryHUD::DrawTurbo(AFuryDirector* Director)
{
	// One turbo gauge per human, home on the left, away on the right.
	const FFurySim& Sim = Director->Sim;
	int32 Count[2] = { 0, 0 };
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		const FFurySeat& Seat = Sim.Seats[i];
		if (!Seat.bActive)
		{
			continue;
		}
		const int32 Row = Count[Seat.Team]++;
		const float W = 214.f;
		const float X = Seat.Team == 0 ? 34.f : 1920.f - 34.f - W;
		const float Y = 1022.f - Row * 50.f;
		Slant(X, Y, W, 40.f, 12.f, Fade(Ink, 0.82f));
		const FFuryPad* Pad = Director->SeatPad(i);
		const bool bCovering = !Director->Seats[i].bBot && Pad && !Pad->bConnected;
		float ChipW = SeatChip(i, X + 8.f, Y + 5.f, 30.f, Director->Seats[i].bBot);
		if (bCovering)
		{
			ChipW += Text(TEXT("CPU"), X + ChipW + 12.f, Y + 5.f, EFuryFace::BoldItalic, 24.f, Gold) + 6.f;
		}
		const bool bFury = Sim.Teams[Seat.Team].InFury();
		const FLinearColor Fill = bFury ? FLinearColor(1.f, 0.5f, 0.05f) : Seat.bTurboSpent ? Fade(Bad, 0.9f) : FLinearColor(0.25f, 0.85f, 1.f);
		Meter(X + ChipW + 14.f, Y + 12.f, W - ChipW - 34.f, 16.f, bFury ? 1.f : Seat.Turbo, Fill, Fade(White, 0.12f));
	}
}

void AFuryHUD::DrawKickMeter(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	const bool bKickPlay = Sim.PlayType == EFuryPlayType::FieldGoal || Sim.PlayType == EFuryPlayType::ExtraPoint;
	if (!bKickPlay || (Sim.Phase != EFuryPhase::Live && Sim.Phase != EFuryPhase::PreSnap))
	{
		return;
	}
	if (!Sim.bKickMeterLive && !Sim.bKickLocked)
	{
		return;
	}
	const float KickYards = Sim.FieldGoalYards();
	const float Sweet = (Sim.CleanKickWidth - Sim.KickScatter) / Sim.KickSpread(KickYards);
	const float X = 660.f, Y = 880.f, W = 600.f, H = 34.f;
	Slant(X - 20.f, Y - 46.f, W + 40.f, H + 66.f, 16.f, Fade(Ink, 0.86f));
	Text(FString::Printf(TEXT("%d YARD %s"), FMath::RoundToInt32(KickYards), Sim.PlayType == EFuryPlayType::ExtraPoint ? TEXT("EXTRA POINT") : TEXT("FIELD GOAL")),
		960.f, Y - 42.f, EFuryFace::Bold, 28.f, Gold, EFuryAlign::Center, 160);
	Rect(X, Y, W, H, Fade(Bad, 0.75f));
	if (KickYards <= Sim.MaxKickYards) { Rect(X + W * 0.5f * (1.f - Sweet), Y, W * Sweet, H, Good); }
	const float Needle = Sim.bKickLocked ? Sim.KickAim : Sim.KickMeter;
	const float NX = X + W * 0.5f * (1.f + Needle);
	Rect(NX - 5.f, Y - 12.f, 10.f, H + 24.f, White);
	Rect(NX - 2.f, Y - 12.f, 4.f, H + 24.f, Ink);
	const int32 Seat = Sim.Captain(Sim.Offense);
	if (Seat != INDEX_NONE && !Sim.bKickLocked)
	{
		Prompts(Seat, { { FuryUI::A, KickYards <= Sim.MaxKickYards ? TEXT("STOP IT IN THE GREEN") : TEXT("KICK  /  OUT OF RANGE") } }, 960.f, Y + H + 14.f, 30.f);
	}
}

// ---------------------------------------------------------------------------------------------
// Tags that follow athletes
// ---------------------------------------------------------------------------------------------

void AFuryHUD::DrawRoutes(AFuryDirector* Director, int32 Seat)
{
	const FFurySim& Sim = Director->Sim;
	static const uint8 Buttons[] = { FuryUI::A, FuryUI::Y, FuryUI::X, FuryUI::A };
	for (const FFurySimPlayer& P : Sim.Players)
	{
		const bool bRunner = P.Job.Job == EFuryJob::Carry || P.Job.Job == EFuryJob::Keeper;
		if (P.Team != Sim.Offense || (!bRunner && P.Job.Job != EFuryJob::Route) || P.Path.IsEmpty()) { continue; }
		const FLinearColor Tint = bRunner ? Blaze : Gold;
		FVector2D Prev;
		bool bProjected = WorldToBoard(FVector(P.P, 8.f), Prev);
		for (int32 i = 0; i < P.Path.Num(); ++i)
		{
			FVector2D Next;
			const bool bNext = WorldToBoard(FVector(P.Path[i], 8.f), Next);
			if (bProjected && bNext)
			{
				Line(Prev, Next, 7.f, Fade(Ink, 0.72f));
				Line(Prev, Next, 3.5f, Tint);
				if (i == P.Path.Num() - 1)
				{
					const FVector2D Dir = (Next - Prev).GetSafeNormal();
					const FVector2D Side(-Dir.Y, Dir.X);
					Triangle(Next + Dir * 6.f, Next - Dir * 13.f + Side * 9.f, Next - Dir * 13.f - Side * 9.f, Tint);
				}
			}
			bProjected = bNext;
			if (bNext) { Prev = Next; }
		}
		FVector2D Tag;
		if (!bRunner && P.PassIcon > 0 && WorldToBoard(FVector(P.P, 252.f), Tag))
		{
			Glyph(Seat, Buttons[P.PassIcon], Tag.X - 17.f, Tag.Y - 30.f, 34.f);
		}
	}
}

void AFuryHUD::DrawFieldTags(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	if (Sim.Phase == EFuryPhase::PlaySelect || Sim.Phase == EFuryPhase::GameOver || Sim.Phase == EFuryPhase::PatSelect)
	{
		return;
	}
	const float Time = Now();
	if (Sim.Phase == EFuryPhase::PreSnap && Sim.OffensePlay() && !Sim.Teams[Sim.Defense()].bHuman &&
		(Sim.PlayType == EFuryPlayType::Scrimmage || Sim.PlayType == EFuryPlayType::TwoPoint))
	{
		const int32 Seat = Sim.Captain(Sim.Offense);
		const FFuryPad* Pad = Director->SeatPad(Seat);
		if (Pad && Pad->IsDown(EFuryButton::LB)) { DrawRoutes(Director, Seat); }
	}

	// Mark the ball in flight and in loose-ball scrambles. Open corners keep the
	// football itself visible against white yard lines and the crowd.
	const EFuryBallState State = Sim.Ball.State;
	if (Sim.Phase == EFuryPhase::Live && (State == EFuryBallState::Pass || State == EFuryBallState::Kick ||
		State == EFuryBallState::FieldGoal || State == EFuryBallState::Loose))
	{
		FVector2D At;
		if (WorldToBoard(Sim.Ball.Pos, At))
		{
			const float Top = FMath::Abs(At.X - 960.f) < 500.f ? 186.f : 38.f;
			const FVector2D Safe(FMath::Clamp(At.X, 35.f, 1885.f), FMath::Clamp(At.Y, Top, 1035.f));
			if (Safe.Equals(At, 1.f))
			{
				for (float Side : {-1.f, 1.f})
				{
					const FVector2D Tip = At + FVector2D(14.f * Side, 0.f);
					const FVector2D A = Tip + FVector2D(5.f * Side, -7.f);
					const FVector2D B = Tip + FVector2D(5.f * Side, 7.f);
					Line(A, Tip, 5.f, Ink); Line(Tip, B, 5.f, Ink);
					Line(A, Tip, 2.f, Gold); Line(Tip, B, 2.f, Gold);
				}
			}
			else
			{
				const FVector2D Dir = (At - Safe).GetSafeNormal();
				const FVector2D Wing(-Dir.Y * 8.f, Dir.X * 8.f);
				Triangle(Safe + Wing, Safe - Wing, Safe + Dir * 15.f, Gold);
				TextShadow(TEXT("BALL"), Safe.X - Dir.X * 20.f, Safe.Y - Dir.Y * 20.f - 14.f, EFuryFace::Bold, 23.f, White, EFuryAlign::Center);
			}
		}
	}

	// Pass icons: the button that throws to each receiver, when a human is at quarterback.
	if (Sim.IsPassIconLive())
	{
		const int32 QB = Sim.Offense * Fury::TeamSize;
		const int32 QBSeat = Sim.Players[QB].Seat;
		const FFuryOffPlay* Play = Sim.OffensePlay();
		if (QBSeat != INDEX_NONE && Play && Play->Kind != EFuryPlayKind::Run)
		{
			static const uint8 Buttons[4] = { FuryUI::A, FuryUI::Y, FuryUI::X, FuryUI::A };
			for (int32 Slot = 0; Slot < Fury::TeamSize; ++Slot)
			{
				const FFurySimPlayer& P = Sim.Players[Sim.Offense * Fury::TeamSize + Slot];
				if (P.PassIcon == 0 || P.bDown)
				{
					continue;
				}
				FVector2D At;
				if (WorldToBoard(FVector(P.P.X, P.P.Y, 235.f), At))
				{
					const float Size = 46.f;
					At.X = FMath::Clamp(At.X, 40.f, 1880.f);
					At.Y = FMath::Clamp(At.Y, 150.f, 1000.f);
					Glyph(QBSeat, Buttons[P.PassIcon], At.X - Size * 0.5f, At.Y - Size - 4.f * FMath::Sin(Time * 6.f + Slot), Size);
				}
			}
		}
	}

	// "P3" over every athlete a human is steering; an arrow at the screen edge if they are out of shot.
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		const FFurySeat& Seat = Sim.Seats[i];
		if (!Seat.bActive || Seat.Player == INDEX_NONE)
		{
			continue;
		}
		const FFurySimPlayer& P = Sim.Players[Seat.Player];
		FVector2D At;
		float TagZ = 205.f;
		if (Sim.AfterWhistle() && P.bDown)
		{
			float Stand = 0.f;
			if (P.Act == EFuryAct::Hit) { Stand = 1.f - Ease(P.ActTime / P.ActLength); }
			if (P.Act == EFuryAct::GetUp) { Stand = Ease(P.ActTime / P.ActLength); }
			TagZ = FMath::Lerp(90.f, 205.f, Stand);
		}
		if (!WorldToBoard(FVector(P.P.X, P.P.Y, TagZ), At))
		{
			continue;
		}
		const FVector2D Projected = At;
		const bool bOff = At.X < 30.f || At.X > 1890.f || At.Y < 140.f || At.Y > 1050.f;
		At.X = FMath::Clamp(At.X, 46.f, 1874.f);
		At.Y = FMath::Clamp(At.Y, 176.f, 1040.f);
		const FLinearColor Color = AFuryDirector::SeatColor(i);
		const float H = 30.f;
		const FString Label = FString::Printf(TEXT("P%d"), i + 1);
		const float W = Measure(Label, EFuryFace::BlackItalic, 24.f).X + 22.f;
		const float Top = At.Y - H - 16.f;
		Rect(At.X - W * 0.5f - 2.f, Top - 2.f, W + 4.f, H + 4.f, Fade(Ink, 0.85f));
		Rect(At.X - W * 0.5f, Top, W, H, Color);
		Text(Label, At.X, Top + 1.f, EFuryFace::BlackItalic, 24.f, InkOn(Color), EFuryAlign::Center);
		const FVector2D Direction = bOff ? (Projected - At).GetSafeNormal() : FVector2D(0.f, 1.f);
		const FVector2D Across(-Direction.Y, Direction.X);
		const float Edge = 1.f / FMath::Max(FMath::Abs(Direction.X) / (W * 0.5f), FMath::Abs(Direction.Y) / (H * 0.5f));
		const FVector2D Base = FVector2D(At.X, Top + H * 0.5f) + Direction * (Edge + 2.f);
		Triangle(Base - Across * 8.f, Base + Across * 8.f, Base + Direction * 11.f, bOff ? White : Color);
	}

	// A marker over a computer-controlled ball carrier so the ball is never lost in a crowd.
	const int32 Carrier = Sim.CarrierIndex();
	if (Carrier != INDEX_NONE && Sim.Players[Carrier].Seat == INDEX_NONE && Sim.Phase == EFuryPhase::Live && !Sim.IsPasser(Carrier))
	{
		FVector2D At;
		if (WorldToBoard(FVector(Sim.Players[Carrier].P.X, Sim.Players[Carrier].P.Y, 215.f), At))
		{
			const float Bob = 4.f * FMath::Sin(Time * 8.f);
			const FLinearColor Color = Bright(Sim.TeamInfo(Sim.Players[Carrier].Team));
			Triangle(FVector2D(At.X - 15.f, At.Y - 30.f + Bob), FVector2D(At.X + 15.f, At.Y - 30.f + Bob), FVector2D(At.X, At.Y - 8.f + Bob), Ink);
			Triangle(FVector2D(At.X - 11.f, At.Y - 28.f + Bob), FVector2D(At.X + 11.f, At.Y - 28.f + Bob), FVector2D(At.X, At.Y - 12.f + Bob), Color);
		}
	}
}

// ---------------------------------------------------------------------------------------------
// Calling plays
// ---------------------------------------------------------------------------------------------

namespace
{
	/** Maps play space (yards: X downfield, Y to the offense's right) into a card. */
	struct FCardSpace
	{
		float X, Y, W, H;
		bool bFlip;
		float Near = -9.f, Far = 21.f;      // yards behind / beyond the line that the card shows
		FVector2D At(FVector2D Yards) const
		{
			const float Lateral = (bFlip ? -Yards.Y : Yards.Y);
			const float U = FMath::Clamp(Lateral / 40.f + 0.5f, 0.03f, 0.97f);
			const float V = FMath::Clamp(1.f - (Yards.X - Near) / (Far - Near), 0.04f, 0.97f);
			return FVector2D(X + U * W, Y + V * H);
		}
		/** Card pixels per yard, for sizing zones. */
		float Scale() const { return FMath::Min(W / 40.f, H / (Far - Near)); }
	};
}

void AFuryHUD::DrawOffenseCard(const FFuryOffPlay& Play, bool bFlip, float X, float Y, float W, float H, const FLinearColor& Accent)
{
	const FCardSpace Space{ X, Y, W, H, bFlip };
	const FLinearColor RouteColor(1.f, 0.82f, 0.12f);
	const FLinearColor RunColor(1.f, 0.42f, 0.1f);
	// Line of scrimmage.
	const FVector2D L0 = Space.At(FVector2D(0.f, -22.f)), L1 = Space.At(FVector2D(0.f, 22.f));
	Line(L0, L1, 2.f, Fade(White, 0.22f));

	for (int32 Slot = 0; Slot < 7; ++Slot)
	{
		const FVector2D Spot = Play.Spot[Slot];
		const FFuryJobSpec& Job = Play.Job[Slot];
		const FVector2D At = Space.At(Spot);
		const bool bRunner = Job.Job == EFuryJob::Carry || Job.Job == EFuryJob::Keeper;

		if (Job.Path.Num() > 0 && Job.Job != EFuryJob::PassBlock && Job.Job != EFuryJob::RunBlock)
		{
			const float Inward = Spot.Y > 0.f ? -1.f : 1.f;
			FVector2D Prev = At;
			const FLinearColor Color = bRunner ? RunColor : Job.Job == EFuryJob::Passer ? Fade(White, 0.6f) : RouteColor;
			for (int32 i = 0; i < Job.Path.Num(); ++i)
			{
				const FVector2D Step = Job.Path[i];
				const FVector2D Next = Space.At(Spot + FVector2D(Step.X, Job.bInward ? Step.Y * Inward : Step.Y));
				Line(Prev, Next, bRunner ? 4.5f : 3.5f, Color);
				if (i == Job.Path.Num() - 1)
				{
					const FVector2D Dir = (Next - Prev).GetSafeNormal();
					const FVector2D Side(-Dir.Y, Dir.X);
					Triangle(Next + Dir * 9.f, Next - Dir * 4.f + Side * 7.f, Next - Dir * 4.f - Side * 7.f, Color);
				}
				Prev = Next;
			}
		}
		else if (Job.Job == EFuryJob::Passer)
		{
			// Straight drop.
			Line(At, Space.At(Spot + FVector2D(-Play.Drop, 0.f)), 2.5f, Fade(White, 0.45f));
		}
		else if (Job.Job == EFuryJob::Punter || Job.Job == EFuryJob::Kicker)
		{
			const FVector2D Up = Space.At(Spot + FVector2D(26.f, 0.f));
			Line(At, Up, 3.5f, RouteColor);
			Triangle(Up + FVector2D(0.f, -9.f), Up + FVector2D(7.f, 4.f), Up + FVector2D(-7.f, 4.f), RouteColor);
		}

		// The player: a ring for linemen, a filled dot for everyone else.
		if (Slot >= 1 && Slot <= 3)
		{
			Rect(At.X - 6.f, At.Y - 6.f, 12.f, 12.f, Fade(White, 0.85f));
		}
		else
		{
			Circle(At, 7.5f, Ink, 14);
			Circle(At, 6.f, Slot == 0 ? Accent : White, 14);
		}
	}
}

void AFuryHUD::DrawDefenseCard(const FFuryDefPlay& Play, bool bFlip, float X, float Y, float W, float H, const FLinearColor& Accent)
{
	FCardSpace Space{ X, Y, W, H, bFlip };
	Space.Near = -7.f;
	Space.Far = 34.f;                       // defenses are drawn deeper so the zones fit on the card
	const FLinearColor RushColor(1.f, 0.3f, 0.2f);
	const FLinearColor ManColor(1.f, 0.82f, 0.12f);
	const FLinearColor ZoneColor(0.25f, 0.6f, 1.f);
	Line(Space.At(FVector2D(0.f, -22.f)), Space.At(FVector2D(0.f, 22.f)), 2.f, Fade(White, 0.22f));

	// A generic offense for reference.
	static const FVector2D Reference[7] = { FVector2D(-5.f, 0.f), FVector2D(-0.4f, 0.f), FVector2D(-0.5f, -1.8f), FVector2D(-0.5f, 1.8f),
		FVector2D(-0.6f, -13.f), FVector2D(-0.6f, 13.f), FVector2D(-5.f, 2.4f) };
	for (const FVector2D& Spot : Reference)
	{
		Circle(Space.At(Spot), 4.f, Fade(White, 0.3f), 10);
	}

	for (int32 Slot = 0; Slot < 7; ++Slot)
	{
		const FFuryJobSpec& Job = Play.Job[Slot];
		FVector2D Spot = Play.Spot[Slot];
		if (Job.Job == EFuryJob::Man && Job.Target >= 0 && Job.Target < 7)
		{
			const FVector2D Receiver = Reference[Job.Target];
			Spot = FVector2D(FMath::Max(Job.Cushion + 0.4f, 1.2f), Receiver.Y * (Receiver.X < -2.f ? 0.6f : 1.f));
			Line(Space.At(Spot), Space.At(Receiver), 2.f, Fade(ManColor, 0.7f));
		}
		const FVector2D At = Space.At(Spot);
		if (Job.Job == EFuryJob::Zone)
		{
			// Kept a little smaller than life so neighbouring zones stay readable.
			const float Radius = FMath::Min(Job.Radius * Space.Scale() * 0.8f, H * 0.3f);
			FVector2D Centre = Space.At(Job.Zone);
			Centre.X = FMath::Clamp(Centre.X, X + Radius + 2.f, X + W - Radius - 2.f);
			Centre.Y = FMath::Clamp(Centre.Y, Y + Radius + 2.f, Y + H - Radius - 2.f);
			Circle(Centre, Radius, Fade(ZoneColor, 0.22f), 20);
			Ring(Centre, Radius, 2.f, Fade(ZoneColor, 0.8f), 20);
		}
		else if (Job.Job == EFuryJob::Rush || Job.Job == EFuryJob::Blitz)
		{
			const FVector2D To = Space.At(FVector2D(-4.f, Spot.Y * 0.35f));
			Line(At, To, Job.Job == EFuryJob::Blitz ? 4.5f : 3.f, RushColor);
			const FVector2D Dir = (To - At).GetSafeNormal();
			const FVector2D Side(-Dir.Y, Dir.X);
			Triangle(To + Dir * 8.f, To - Dir * 3.f + Side * 6.f, To - Dir * 3.f - Side * 6.f, RushColor);
		}
		else if (Job.Job == EFuryJob::Spy)
		{
			Ring(At, 12.f, 2.5f, ManColor, 16);
		}
		const FLinearColor Mark = Job.Job == EFuryJob::Blitz ? RushColor : Job.Job == EFuryJob::Zone ? ZoneColor : White;
		Line(At + FVector2D(-6.f, -6.f), At + FVector2D(6.f, 6.f), 3.5f, Mark);
		Line(At + FVector2D(-6.f, 6.f), At + FVector2D(6.f, -6.f), 3.5f, Mark);
	}
}

void AFuryHUD::DrawPickPanel(AFuryDirector* Director, int32 Team, float X, float Y, float W, float H)
{
	const FFurySim& Sim = Director->Sim;
	const FFuryPick& Pick = Sim.Picks[Team];
	const FFuryTeam& Info = Sim.TeamInfo(Team);
	const bool bOffense = Team == Sim.Offense;
	const int32 Seat = Sim.Captain(Team);
	const FLinearColor Accent = Bright(Info);
	const float Time = Now();

	Panel(X, Y, W, H, Info.Primary, 0.9f);
	GradientH(X, Y + 5.f, W, 64.f, Fade(Info.Primary, 0.9f), Fade(Info.Primary, 0.25f));
	const FLinearColor HeadInk = InkOn(Info.Primary);
	Text(FString::Printf(TEXT("%s  %s"), *Info.Abbr, bOffense ? TEXT("OFFENSE") : TEXT("DEFENSE")), X + 22.f, Y + 12.f, EFuryFace::BlackItalic, 44.f, HeadInk);
	if (Seat != INDEX_NONE)
	{
		const float ChipX = X + W - 250.f;
		Text(TEXT("CALLS IT"), ChipX + 96.f, Y + 22.f, EFuryFace::Bold, 24.f, HeadInk == Ink ? Ink : Fade(White, 0.8f), EFuryAlign::Left, 100);
		SeatChip(Seat, ChipX, Y + 14.f, 42.f);
	}
	else
	{
		SeatChip(0, X + W - 130.f, Y + 14.f, 42.f, true);
	}

	const float GridX = X + 20.f, GridY = Y + 84.f, Gap = 12.f;
	const float CardW = (W - 40.f - 2.f * Gap) / 3.f;
	const float CardH = (H - 84.f - 76.f - 2.f * Gap) / 3.f;

	if (Seat == INDEX_NONE)
	{
		// The computer does not show its hand.
		const FString Dots = FString::ChrN(1 + (static_cast<int32>(Time * 3.f) % 3), TEXT('.'));
		Text(Pick.bLocked ? TEXT("READY") : TEXT("THINKING") + Dots, X + W * 0.5f, Y + H * 0.5f - 50.f, EFuryFace::BlackItalic, 96.f, Pick.bLocked ? Good : Fade(White, 0.5f), EFuryAlign::Center);
		return;
	}
	if (Pick.bLocked)
	{
		// Chosen plays are hidden so the other bench cannot read them off the screen.
		Slant(X + 60.f, Y + H * 0.5f - 70.f, W - 120.f, 140.f, 40.f, Good);
		Text(TEXT("PLAY IS IN"), X + W * 0.5f + 20.f, Y + H * 0.5f - 60.f, EFuryFace::BlackItalic, 100.f, Ink, EFuryAlign::Center);
		return;
	}

	for (int32 Cell = 0; Cell < 9; ++Cell)
	{
		const float CX = GridX + (Cell % 3) * (CardW + Gap), CY = GridY + (Cell / 3) * (CardH + Gap);
		const bool bHot = Pick.Cursor == Cell;
		const FFuryOffPlay* Off = bOffense ? Sim.OffenseChoice(Pick.Page, Cell) : nullptr;
		const FFuryDefPlay* Def = bOffense ? nullptr : Sim.DefenseChoice(Cell);
		if (!Off && !Def)
		{
			Rect(CX, CY, CardW, CardH, Fade(White, 0.03f));
			continue;
		}
		Rect(CX, CY, CardW, CardH, bHot ? FLinearColor(0.1f, 0.13f, 0.1f, 0.96f) : FLinearColor(0.03f, 0.07f, 0.045f, 0.92f));
		if (Off)
		{
			DrawOffenseCard(*Off, Pick.bFlip, CX + 6.f, CY + 4.f, CardW - 12.f, CardH - 44.f, Accent);
		}
		else
		{
			DrawDefenseCard(*Def, Pick.bFlip, CX + 6.f, CY + 4.f, CardW - 12.f, CardH - 44.f, Accent);
		}
		const FString& Name = Off ? Off->Name : Def->Name;
		Rect(CX, CY + CardH - 40.f, CardW, 40.f, bHot ? AFuryDirector::SeatColor(Seat) : Fade(Ink, 0.9f));
		Text(Name, CX + CardW * 0.5f, CY + CardH - 37.f, EFuryFace::BoldItalic, 28.f, bHot ? InkOn(AFuryDirector::SeatColor(Seat)) : White, EFuryAlign::Center, 20);
		if (bHot)
		{
			const float Thick = 4.f + 1.5f * FMath::Sin(Time * 9.f);
			Frame(CX - 2.f, CY - 2.f, CardW + 4.f, CardH + 4.f, Thick, AFuryDirector::SeatColor(Seat));
		}
		if (Off && Off->Kind == EFuryPlayKind::FieldGoal)
		{
			const float Yards = Sim.FieldGoalYards();
			const bool bLong = Yards > Sim.MaxKickYards;
			const FString Label = FString::Printf(TEXT("%d YD%s"), FMath::RoundToInt32(Yards), bLong ? TEXT("  /  OUT OF RANGE") : TEXT(""));
			Text(Label, CX + 8.f, CY + 4.f, EFuryFace::Bold, 20.f, bLong ? Gold : White);
		}
		else if (Off && Off->Kind == EFuryPlayKind::Run)
		{
			Text(TEXT("RUN"), CX + 8.f, CY + 4.f, EFuryFace::Bold, 18.f, FLinearColor(1.f, 0.5f, 0.15f), EFuryAlign::Left, 100);
		}
	}

	// What the highlighted play is for, the page, and the buttons.
	const float FootY = Y + H - 70.f;
	const FFuryOffPlay* HotOff = bOffense ? Sim.OffenseChoice(Pick.Page, Pick.Cursor) : nullptr;
	const FFuryDefPlay* HotDef = bOffense ? nullptr : Sim.DefenseChoice(Pick.Cursor);
	const FString Tagline = HotOff ? HotOff->Tagline : HotDef ? HotDef->Tagline : FString();
	Text(Tagline + (Pick.bFlip ? TEXT("   (FLIPPED)") : TEXT("")), X + 22.f, FootY, EFuryFace::BoldItalic, 26.f, Fade(White, 0.85f));
	if (bOffense)
	{
		static const TCHAR* Pages[3] = { TEXT("PASS"), TEXT("RUN & TRICK"), TEXT("KICK") };
		float PX = X + W - 22.f;
		for (int32 Page = 2; Page >= 0; --Page)
		{
			const float PW = Measure(Pages[Page], EFuryFace::Bold, 22.f, 80).X + 26.f;
			PX -= PW;
			Rect(PX, FootY - 2.f, PW - 6.f, 32.f, Pick.Page == Page ? Accent : Fade(White, 0.08f));
			Text(Pages[Page], PX + (PW - 6.f) * 0.5f, FootY, EFuryFace::Bold, 22.f, Pick.Page == Page ? InkOn(Accent) : Dim, EFuryAlign::Center, 80);
		}
	}
	if (bOffense)
	{
		Prompts(Seat, { { FuryUI::A, TEXT("CALL IT") }, { FuryUI::X, TEXT("FLIP") }, { FuryUI::RB, TEXT("PAGE") } }, X + W * 0.5f, FootY + 36.f, 26.f);
	}
	else
	{
		Prompts(Seat, { { FuryUI::A, TEXT("CALL IT") }, { FuryUI::X, TEXT("FLIP") } }, X + W * 0.5f, FootY + 36.f, 26.f);
	}
}

void AFuryHUD::DrawPlaySelect(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	const float In = Ease(Sim.PhaseTime / 0.3f);
	ScreenShade(Fade(Ink, 0.45f * In));
	const float PanelW = 880.f, PanelH = 770.f, Y = 190.f + 60.f * (1.f - In);
	DrawPickPanel(Director, 0, 40.f - 300.f * (1.f - In), Y, PanelW, PanelH);
	DrawPickPanel(Director, 1, 1000.f + 300.f * (1.f - In), Y, PanelW, PanelH);

	// Shared clock between the two panels.
	const bool bAnyHuman = Sim.Captain(0) != INDEX_NONE || Sim.Captain(1) != INDEX_NONE;
	if (bAnyHuman)
	{
		const float Left = FMath::Max(0.f, Sim.SelectTimer);
		const FVector2D Centre(960.f, Y + 60.f);
		Circle(Centre, 40.f, Fade(Ink, 0.92f), 28);
		Ring(Centre, 34.f, 6.f, Left < 4.f ? Bad : Gold, 40, 0.f, FMath::Clamp(Left / 14.f, 0.f, 1.f));
		Text(FString::FromInt(FMath::CeilToInt32(Left)), 960.f, Centre.Y - 22.f, EFuryFace::BlackItalic, 40.f, White, EFuryAlign::Center);
	}
}

void AFuryHUD::DrawPatSelect(AFuryDirector* Director)
{
	const FFurySim& Sim = Director->Sim;
	if (Sim.ScoringTeam == INDEX_NONE)
	{
		return;
	}
	const FFuryTeam& Info = Sim.TeamInfo(Sim.ScoringTeam);
	const int32 Seat = Sim.Captain(Sim.ScoringTeam);
	const float In = Ease(Sim.PhaseTime / 0.3f);
	const float X = 500.f, Y = 360.f + 50.f * (1.f - In), W = 920.f, H = 330.f;
	ScreenShade(Fade(Ink, 0.4f * In));
	Panel(X, Y, W, H, Info.Primary, 0.92f);
	Text(TEXT("AFTER THE TOUCHDOWN"), X + W * 0.5f, Y + 20.f, EFuryFace::Bold, 30.f, Dim, EFuryAlign::Center, 300);
	const TCHAR* Titles[2] = { TEXT("KICK IT"), TEXT("GO FOR TWO") };
	const TCHAR* Notes[2] = { TEXT("+1  SAFE"), TEXT("+2  FROM THE 3") };
	for (int32 i = 0; i < 2; ++i)
	{
		const bool bHot = Sim.PatChoice == i && Seat != INDEX_NONE;
		const float CX = X + 40.f + i * 430.f, CW = 410.f;
		Slant(CX, Y + 80.f, CW, 150.f, 34.f, bHot ? Bright(Info) : Fade(White, 0.07f));
		const FLinearColor TextColor = bHot ? InkOn(Bright(Info)) : Fade(White, 0.75f);
		Text(Titles[i], CX + CW * 0.5f + 17.f, Y + 88.f, EFuryFace::BlackItalic, 72.f, TextColor, EFuryAlign::Center);
		Text(Notes[i], CX + CW * 0.5f + 17.f, Y + 172.f, EFuryFace::Bold, 28.f, TextColor, EFuryAlign::Center, 160);
	}
	if (Seat != INDEX_NONE)
	{
		const float ChipW = SeatChip(Seat, X + 40.f, Y + H - 62.f, 40.f);
		Text(TEXT("DECIDES"), X + 40.f + ChipW + 10.f, Y + H - 56.f, EFuryFace::Bold, 26.f, Dim, EFuryAlign::Left, 120);
		Prompts(Seat, { { FuryUI::Stick, TEXT("CHOOSE") }, { FuryUI::A, TEXT("GO") } }, X + W * 0.5f + 120.f, Y + H - 62.f, 30.f);
	}
	else
	{
		Text(TEXT("COMPUTER IS DECIDING..."), X + W * 0.5f, Y + H - 62.f, EFuryFace::BoldItalic, 34.f, Fade(White, 0.6f), EFuryAlign::Center);
	}
}

// ---------------------------------------------------------------------------------------------
// The stadium's video board
// ---------------------------------------------------------------------------------------------

void AFuryHUD::DrawBoard(AFuryDirector* Director)
{
	AFuryStadium* Stadium = Director->GetStadium();
	UTextureRenderTarget2D* Target = Stadium ? Stadium->BoardTarget() : nullptr;
	if (!Target)
	{
		return;
	}
	const FFurySim& Sim = Director->Sim;
	const FFuryBanner& Banner = Director->Banner;
	const bool bBanner = !Banner.Title.IsEmpty() && Now() - Banner.Start < Banner.Length;
	const FString Headline = bBanner ? Banner.Title : Sim.DownText();
	const FString Foot = Sim.bOvertime ? FString(TEXT("SUDDEN DEATH")) : FString::Printf(TEXT("%s   %s"), QuarterName(Sim.Quarter), *Sim.ClockText());
	const FString Content = FString::Printf(TEXT("%d/%d/%d/%d/%d/%s/%s"), Sim.Teams[0].League, Sim.Teams[1].League,
		Sim.Teams[0].Score, Sim.Teams[1].Score, bBanner, *Headline, *Foot);
	if (Content == LastBoardContent) { return; }
	// Borrow the kit: point it at the board's canvas for a moment.
	UCanvas* Saved = Canvas;
	const float SavedS = S, SavedX = OX, SavedY = OY;
	UCanvas* BoardCanvas = nullptr;
	FVector2D Size;
	FDrawToRenderTargetContext Context;
	UKismetRenderingLibrary::BeginDrawCanvasToRenderTarget(this, Target, BoardCanvas, Size, Context);
	if (BoardCanvas)
	{
		Canvas = BoardCanvas;
		S = Size.X / 1920.f;
		OX = OY = 0.f;

		LastBoardContent = Content;
		const FFuryTeam& Home = Sim.TeamInfo(0);
		const FFuryTeam& Away = Sim.TeamInfo(1);
		GradientV(0.f, 0.f, 1920.f, 1080.f, FLinearColor(0.02f, 0.03f, 0.07f), FLinearColor(0.005f, 0.008f, 0.02f));
		for (int32 Team = 0; Team < 2; ++Team)
		{
			const FFuryTeam& Info = Team == 0 ? Home : Away;
			const float X = Team == 0 ? 60.f : 1010.f;
			Slant(X, 60.f, 850.f, 420.f, 90.f, Info.Primary);
			if (UTexture* Logo = Director->TeamLogo(Sim.Teams[Team].League))
			{
				Image(Logo, X + 110.f, 90.f, 360.f, 360.f);
			}
			Text(FString::FromInt(Sim.Teams[Team].Score), X + 780.f, 60.f, EFuryFace::BlackItalic, 330.f, InkOn(Info.Primary), EFuryAlign::Right);
		}
		const float MaxSize = 235.f;
		const float TitleSize = MaxSize * FMath::Min(1.f, 1780.f / FMath::Max(1.f, static_cast<float>(Measure(Headline, EFuryFace::BlackItalic, MaxSize).X)));
		Text(Headline, 960.f, 648.f - TitleSize * 0.55f, EFuryFace::BlackItalic, TitleSize, bBanner ? Gold : White, EFuryAlign::Center);
		Text(Foot, 960.f, 860.f, EFuryFace::Bold, 120.f, Dim, EFuryAlign::Center, 200);
	}
	UKismetRenderingLibrary::EndDrawCanvasToRenderTarget(this, Context);
	Canvas = Saved;
	S = SavedS;
	OX = SavedX;
	OY = SavedY;
}
