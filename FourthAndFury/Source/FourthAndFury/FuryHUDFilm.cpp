#include "FuryHUD.h"

#include "Algo/BinarySearch.h"
#include "FuryDirector.h"
#include "FuryHUDStyle.h"

using namespace FuryUI;

void AFuryHUD::DrawFilm(AFuryDirector* Director)
{
	const FFuryPlayFilm& Film = Director->SelectedFilm();
	if (!Film.Ready()) { return; }
	const float Time = Director->FilmTime;
	const float Duration = Film.Duration();
	const int32 Next = FMath::Clamp(Algo::UpperBoundBy(Film.Frames, Time, &FFuryFilmFrame::Time), 1, Film.Frames.Num() - 1);
	const FFuryFilmFrame& AFrame = Film.Frames[Next - 1];
	const FFuryFilmFrame& BFrame = Film.Frames[Next];
	const float Alpha = FMath::Clamp((Time - AFrame.Time) / (BFrame.Time - AFrame.Time), 0.f, 1.f);
	const FFuryFilmFrame& Active = Alpha < 0.5f ? AFrame : BFrame;

	constexpr float X = 278.f, Y = 218.f, W = 1364.f, H = 606.f;
	auto At = [](FVector2f P)
	{
		return FVector2D(X + W * (0.5f + P.X / (2.f * Fury::EndLineX)), Y + H * (0.5f + P.Y / (2.f * Fury::SidelineY)));
	};
	ScreenShade(FLinearColor(0.033f, 0.045f, 0.063f), Ink);
	Text(Director->Screen == EFuryScreen::Final && Director->Film.LongestTouchdown.Ready() ? TEXT("LONGEST TOUCHDOWN") : TEXT("PLAY FILM"), X, 47.f, EFuryFace::BlackItalic, 82.f, White);
	const FString Subhead = Film.ScoreLine.IsEmpty() ? FString::Printf(TEXT("%s    /    %s    /    %s"), *Director->Sim.TeamInfo(Film.Offense).Abbr, *Film.DownText, *Film.Result) : Film.ScoreLine;
	Text(Subhead, X + 4.f, 153.f, EFuryFace::Bold, 31.f, Gold);
	const FString Period = Film.Quarter > 4 ? FString(TEXT("OT")) : FString::Printf(TEXT("Q%d"), Film.Quarter);
	Text(Period + TEXT("    ") + Film.Clock, X + W, 83.f, EFuryFace::BlackItalic, 48.f, White, EFuryAlign::Right);

	const float Ten = W / 12.f;
	const FLinearColor FieldA(0.035f, 0.112f, 0.088f), FieldB(0.044f, 0.135f, 0.101f);
	FLinearColor Colors[2];
	Rect(X, Y, W, H, FieldA);
	for (int32 Team = 0; Team < 2; ++Team)
	{
		const FFuryTeam& Info = Director->Sim.TeamInfo(Team);
		Colors[Team] = Info.Primary.GetLuminance() < 0.085f ? Info.Secondary : Info.Primary;
		const float Start = Team == 0 ? X : X + W - Ten;
		Rect(Start, Y, Ten, H, FMath::Lerp(Ink, Info.Primary, 0.7f));
		if (UTexture* Logo = Director->TeamLogo(Director->Sim.Teams[Team].League))
		{
			Image(Logo, Start + 8.f, Y + H * 0.5f - 49.f, Ten - 16.f, Ten - 16.f);
		}
	}
	for (int32 Yard = 0; Yard <= 100; Yard += 5)
	{
		const float L = X + Ten * (1.f + Yard * 0.1f);
		if (Yard % 10 == 0 && Yard < 100) { Rect(L, Y, Ten * 0.5f, H, FieldB); }
		const float Strength = Yard % 10 == 0 ? 0.36f : 0.14f;
		Rect(L - 1.f, Y, 2.f, H, Fade(White, Strength));
		if (Yard > 0 && Yard < 100 && Yard % 10 == 0)
		{
			const FString Label = FString::FromInt(FMath::Min(Yard, 100 - Yard));
			for (float Edge : { Y + 12.f, Y + H - 40.f })
			{
				Text(Label, L, Edge, EFuryFace::BoldItalic, 24.f, Fade(White, 0.5f), EFuryAlign::Center);
			}
		}
	}
	if (Film.bChains)
	{
		Rect(At(FVector2f(Film.Los, 0.f)).X, Y, 3.f, H, Fade(FLinearColor(0.2f, 0.56f, 1.f), 0.85f));
		Rect(At(FVector2f(Film.ToGain, 0.f)).X, Y, 3.f, H, Fade(Gold, 0.85f));
	}
	Frame(X, Y, W, H, 3.f, Fade(White, 0.8f));

	// The trail follows only the ball. All fourteen numbers are the actual jerseys from the snap.
	const FVector2D Ball = At(FMath::Lerp(AFrame.Ball, BFrame.Ball, Alpha));
	FVector2D Tip = Ball;
	for (int32 j = Next - 1; j >= 0 && Time - Film.Frames[j].Time < 0.85f; --j)
	{
		const FVector2D Previous = At(Film.Frames[j].Ball);
		Line(Previous, Tip, 4.5f, Fade(Gold, FMath::Clamp(1.f - (Time - Film.Frames[j].Time) / 0.85f, 0.f, 1.f)));
		Tip = Previous;
	}
	for (int32 i = 0; i < Fury::NumPlayers; ++i)
	{
		const int32 Team = i / Fury::TeamSize;
		const FVector2D P = At(FMath::Lerp(AFrame.Athlete[i], BFrame.Athlete[i], Alpha));
		const bool bDown = (Active.Down & (1u << i)) != 0;
		const float R = bDown ? 11.f : 14.f;
		if (i == Active.Holder) { Ring(P, R + 5.f, 3.f, Gold, 24); }
		if (Team == 0)
		{
			Circle(P, R + 2.f, White, 20);
			Circle(P, R, Colors[Team], 20);
		}
		else
		{
			Rect(P.X-R-2.f, P.Y-R-2.f, 2.f*R+4.f, 2.f*R+4.f, White);
			Rect(P.X-R, P.Y-R, 2.f*R, 2.f*R, Colors[Team]);
		}
		Text(FString::FromInt(Film.Number[i]), P.X, P.Y - R * 0.88f, EFuryFace::Black, R * 1.48f, InkOn(Colors[Team]), EFuryAlign::Center);
	}
	if (Active.Holder == INDEX_NONE)
	{
		Circle(Ball, 9.f, Ink, 20);
		Circle(Ball, 6.f, Gold, 20);
	}
	const float FY = 889.f;
	const float Playhead = X + W * Time / Duration;
	const float Whistle = X + W * Film.Whistle / Duration;
	Rect(X, FY, W, 7.f, Slate);
	Rect(X, FY, Playhead - X, 7.f, Gold);
	const FFuryPlayFilm::FMoment* Call = nullptr;
	for (const FFuryPlayFilm::FMoment& Moment : Film.Moments)
	{
		Rect(X + W * Moment.Time / Duration - 1.f, FY - 4.f, 2.f, 4.f, Dim);
		if (Moment.Time <= Time) { Call = &Moment; }
	}
	if (Call)
	{
		const int32 i = Call->Athlete;
		const FFuryTeam& Team = Director->Sim.TeamInfo(i / Fury::TeamSize);
		const FString Caption = FString::Printf(TEXT("%s    /    %s  #%d  %s"), *Call->Action.ToString(), *Team.Abbr, Film.Number[i], *Team.Roster[Film.Roster[i]].Name.ToUpper());
		Text(Caption, X, FY - 46.f, EFuryFace::BoldItalic, 30.f, White);
	}
	Rect(Whistle - 1.f, FY - 5.f, 2.f, 17.f, White);
	Circle(FVector2D(Playhead, FY + 3.f), 8.f, Gold, 18);
	Text(TEXT("WHISTLE"), FMath::Min(Whistle, X+W-100.f), FY + 16.f, EFuryFace::Bold, 19.f, Dim);
	Text(FString::Printf(TEXT("%.1f / %.1f s"), Time, Duration), X+W, FY - 46.f, EFuryFace::SemiBold, 28.f, White, EFuryAlign::Right);
	Prompts(Director->PauseSeat, {{A, Director->bFilmRolling ? TEXT("PAUSE FILM") : Time >= Duration ? TEXT("PLAY AGAIN") : TEXT("PLAY")}, {Stick, TEXT("LEFT / RIGHT TO SCRUB")}, {B, TEXT("BACK")}}, 960.f, 964.f, 34.f);
}
