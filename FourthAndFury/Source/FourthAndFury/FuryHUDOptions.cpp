#include "FuryHUD.h"
#include "FuryDirector.h"
#include "FuryHUDStyle.h"

using namespace FuryUI;

void AFuryHUD::DrawSettings(AFuryDirector* Director)
{
	const FFuryOptions& Options = Director->Options;
	const bool bSound = Director->bSoundTab;
	const float Left = 54.f, Width = 820.f, RowY = 235.f, Step = 58.f;
	const int32 Rows = bSound ? FFuryOptions::SoundRows : FFuryOptions::GraphicsRows;
	const int32 First = bSound ? FFuryOptions::GraphicsRows : 0;
	const float Bottom = RowY + Rows * Step + 145.f;
	Panel(Left, 62.f, Width, Bottom - 62.f, Blaze, 0.97f);
	Text(TEXT("SETTINGS"), Left + 34.f, 73.f, EFuryFace::BlackItalic, 69.f, White);

	Glyph(INDEX_NONE, LB, Left + 38.f, 170.f, 32.f);
	Text(TEXT("GRAPHICS"), Left + 138.f, 159.f, EFuryFace::ExtraBold, 36.f, bSound ? Dim : White);
	Text(TEXT("SOUND"), Left + 366.f, 159.f, EFuryFace::ExtraBold, 36.f, bSound ? White : Dim);
	Glyph(INDEX_NONE, RB, Left + 525.f, 170.f, 32.f);
	Rect(Left + 36.f, 215.f, Width - 72.f, 2.f, Slate);
	Rect(Left + (bSound ? 366.f : 138.f), 213.f, bSound ? 102.f : 141.f, 5.f, Blaze);

	for (int32 i = 0; i < Rows; ++i)
	{
		const EFuryOption Id = static_cast<EFuryOption>(First + i);
		const bool bSelected = i == Director->SettingsRow;
		const float YPos = RowY + Step * i;
		if (bSelected)
		{
			Rect(Left + 23.f, YPos, Width - 46.f, Step - 3.f, FLinearColor(0.135f, 0.072f, 0.042f));
			Rect(Left + 23.f, YPos, 5.f, Step - 3.f, Blaze);
		}
		Text(FFuryOptions::Label(Id), Left + 42.f, YPos + 7.f, EFuryFace::SemiBold, 32.f, bSelected ? White : Dim);
		if (FFuryOptions::IsChannel(Id))
		{
			Meter(Left + 360.f, YPos + 24.f, 222.f, 11.f, Options.Volume(Id), bSelected ? Gold : Dim, Slate);
		}
		Text(Options.Display(Id), Left + Width - 73.f, YPos + 6.f, EFuryFace::Bold, 33.f, bSelected ? Gold : White, EFuryAlign::Right);
		if (bSelected)
		{
			Text(TEXT("<"), Left + (FFuryOptions::IsChannel(Id) ? 326.f : 521.f), YPos + 7.f, EFuryFace::Bold, 30.f, Blaze);
			Text(TEXT(">"), Left + Width - 52.f, YPos + 7.f, EFuryFace::Bold, 30.f, Blaze);
		}
	}
	const float Foot = RowY + Rows * Step;
	Rect(Left + 36.f, Foot + 12.f, Width - 72.f, 2.f, Slate);
	Text(FFuryOptions::Hint(static_cast<EFuryOption>(First + Director->SettingsRow)),
		Left + 42.f, Foot + 24.f, EFuryFace::Medium, 27.f, White);
	if (FFuryOptions::IsChannel(static_cast<EFuryOption>(First + Director->SettingsRow)))
	{
		Prompts(INDEX_NONE, {{Stick,TEXT("ADJUST")}, {A,TEXT("LISTEN")}, {Y,Options.Muted(static_cast<EFuryOption>(First + Director->SettingsRow)) ? TEXT("UNMUTE") : TEXT("MUTE")}, {X,TEXT("RESET SOUND")}, {B,TEXT("BACK")}},
			Left + Width * 0.5f, Foot + 85.f, 23.f);
	}
	else
	{
		Prompts(INDEX_NONE, {{Stick,TEXT("ADJUST")}, {X, bSound ? TEXT("RESET SOUND") : TEXT("RESET GRAPHICS")}, {B,TEXT("BACK")}},
			Left + Width * 0.5f, Foot + 85.f, 24.f);
	}

	if (bSound) { return; }
	const float XPos = 1430.f, YPos = 62.f;
	Panel(XPos, YPos, 436.f, 250.f, Blaze, 0.94f);
	Text(TEXT("VISUAL QUALITY"), XPos + 26.f, YPos + 17.f, EFuryFace::Bold, 25.f, Dim, EFuryAlign::Left, 100);
	const int32 Bars = FMath::RoundToInt(Options.Detail(Director->RenderPercent) * 12.f);
	for (int32 i = 0; i < 12; ++i)
	{
		Slant(XPos + 26.f + 32.f * i, YPos + 59.f, 26.f, 11.f, 4.f, i < Bars ? Gold : Slate);
	}
	const FString FPS = Director->LiveFPS > 0.f ? FString::Printf(TEXT("%.0f FPS"), Director->LiveFPS) : TEXT("-- FPS");
	Text(FPS, XPos + 25.f, YPos + 79.f, EFuryFace::ExtraBoldItalic, 61.f, White);
	if (Director->LiveFPS > 0.f)
	{
		Text(FString::Printf(TEXT("%.1f ms"), 1000.f / Director->LiveFPS), XPos + 409.f, YPos + 103.f,
			EFuryFace::SemiBold, 32.f, White, EFuryAlign::Right);
	}
	Text(TEXT("Live frame time  /  120 FPS takes 8.3 ms"), XPos + 27.f, YPos + 156.f, EFuryFace::Medium, 24.f, Dim);
	const FIntPoint Size = Director->OutputSize;
	Text(FString::Printf(TEXT("Field   %d x %d   /   %.0f%%"), FMath::RoundToInt(Size.X * Director->RenderPercent / 100.f),
		FMath::RoundToInt(Size.Y * Director->RenderPercent / 100.f), Director->RenderPercent),
		XPos + 27.f, YPos + 197.f, EFuryFace::SemiBold, 25.f, White);
}
