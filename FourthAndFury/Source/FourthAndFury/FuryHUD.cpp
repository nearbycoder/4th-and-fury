#include "FuryHUD.h"

#include "CanvasItem.h"
#include "Engine/Canvas.h"
#include "Engine/Font.h"
#include "Engine/Texture.h"
#include "Engine/Texture2D.h"
#include "Fonts/CompositeFont.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "FuryAudio.h"
#include "FuryDirector.h"
#include "FuryGame.h"
#include "FuryHUDStyle.h"
#include "FuryInput.h"
#include "Misc/Paths.h"
#include "RenderUtils.h"
#include "Rendering/SlateRenderer.h"
#include "TextureResource.h"

namespace
{
	const TCHAR* FaceFiles[static_cast<int32>(EFuryFace::Count)] = {
		TEXT("BarlowCondensed-Medium.ttf"), TEXT("BarlowCondensed-SemiBold.ttf"), TEXT("BarlowCondensed-Bold.ttf"),
		TEXT("BarlowCondensed-ExtraBold.ttf"), TEXT("BarlowCondensed-Black.ttf"), TEXT("BarlowCondensed-BoldItalic.ttf"),
		TEXT("BarlowCondensed-ExtraBoldItalic.ttf"), TEXT("BarlowCondensed-BlackItalic.ttf"), TEXT("Anton-Regular.ttf"),
		TEXT("Graduate-Regular.ttf"),
	};
	const FName FaceNames[static_cast<int32>(EFuryFace::Count)] = {
		TEXT("Medium"), TEXT("SemiBold"), TEXT("Bold"), TEXT("ExtraBold"), TEXT("Black"), TEXT("BoldItalic"),
		TEXT("ExtraBoldItalic"), TEXT("BlackItalic"), TEXT("Anton"), TEXT("Graduate"),
	};

	FCanvasUVTri MakeTri(FVector2D A, FVector2D B, FVector2D C, const FLinearColor& CA, const FLinearColor& CB, const FLinearColor& CC)
	{
		FCanvasUVTri Tri;
		Tri.V0_Pos = A; Tri.V1_Pos = B; Tri.V2_Pos = C;
		Tri.V0_UV = Tri.V1_UV = Tri.V2_UV = FVector2D::ZeroVector;
		Tri.V0_Color = CA; Tri.V1_Color = CB; Tri.V2_Color = CC;
		return Tri;
	}
}

float AFuryHUD::Now() const
{
	return GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.f;
}

void AFuryHUD::BuildFont()
{
	// The canvas draws text from a font object, so wrap the game's TTF files (one typeface entry
	// per EFuryFace) in a runtime-cached font.
	UIFont = NewObject<UFont>(this, TEXT("FuryUIFont"));
	UIFont->FontCacheType = EFontCacheType::Runtime;
	FCompositeFont& Composite = UIFont->GetMutableInternalCompositeFont();
	const FString Dir = FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("Fonts"));
	for (int32 i = 0; i < static_cast<int32>(EFuryFace::Count); ++i)
	{
		Composite.DefaultTypeface.Fonts.Add(FTypefaceEntry(FaceNames[i], Dir / FaceFiles[i], EFontHinting::Default, EFontLoadingPolicy::LazyLoad));
	}
}

FSlateFontInfo AFuryHUD::Font(EFuryFace Face, float Size, int32 Spacing) const
{
	// Size is the em height in board pixels; Slate sizes are points at 96 DPI. Whole sizes only,
	// so animated text reuses a small set of cached glyphs.
	FSlateFontInfo Info(UIFont, FMath::Max(1.f, FMath::RoundToFloat(Size * S * 0.75f)), FaceNames[static_cast<int32>(Face)]);
	Info.LetterSpacing = Spacing;
	return Info;
}

FVector2D AFuryHUD::Measure(const FString& Str, EFuryFace Face, float Size, int32 Spacing) const
{
	const FSlateFontInfo Info = Font(Face, Size, Spacing);
	if (FSlateApplication::IsInitialized() && FSlateApplication::Get().GetRenderer())
	{
		const FVector2D Pixels = FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Str, Info);
		return Pixels / S;
	}
	return FVector2D(Str.Len() * Size * 0.5f, Size * 1.2f);
}

void AFuryHUD::Stamp(const FString& Str, float ScreenX, float ScreenY, const FSlateFontInfo& FontInfo, const FLinearColor& Color)
{
	FCanvasTextItem Item(FVector2D(ScreenX, ScreenY), FText::FromString(Str), FontInfo, Color);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

float AFuryHUD::Text(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, EFuryAlign Align, int32 Spacing)
{
	const float Width = Measure(Str, Face, Size, Spacing).X;
	const float Left = Align == EFuryAlign::Center ? X - Width * 0.5f : Align == EFuryAlign::Right ? X - Width : X;
	const FVector2D P = ToScreen(FVector2D(Left, Y));
	Stamp(Str, FMath::RoundToFloat(P.X), FMath::RoundToFloat(P.Y), Font(Face, Size, Spacing), Color);
	return Width;
}

float AFuryHUD::TextShadow(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, EFuryAlign Align, int32 Spacing, float Offset)
{
	Text(Str, X + Offset, Y + Offset, Face, Size, FLinearColor(0.f, 0.f, 0.f, 0.75f * Color.A), Align, Spacing);
	return Text(Str, X, Y, Face, Size, Color, Align, Spacing);
}

float AFuryHUD::TextOutline(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, const FLinearColor& Outline, float Thickness, EFuryAlign Align, int32 Spacing)
{
	const float Width = Measure(Str, Face, Size, Spacing).X;
	const float Left = Align == EFuryAlign::Center ? X - Width * 0.5f : Align == EFuryAlign::Right ? X - Width : X;
	const FVector2D P = ToScreen(FVector2D(Left, Y));
	const FSlateFontInfo Info = Font(Face, Size, Spacing);
	const float R = FMath::Max(1.f, Thickness * S);
	const FLinearColor Edge(Outline.R, Outline.G, Outline.B, Outline.A * Color.A);
	constexpr int32 Copies = 12;
	for (int32 i = 0; i < Copies; ++i)
	{
		const float Angle = UE_TWO_PI * i / Copies;
		Stamp(Str, FMath::RoundToFloat(P.X + FMath::Cos(Angle) * R), FMath::RoundToFloat(P.Y + FMath::Sin(Angle) * R), Info, Edge);
	}
	Stamp(Str, FMath::RoundToFloat(P.X), FMath::RoundToFloat(P.Y), Info, Color);
	return Width;
}

void AFuryHUD::Rect(float X, float Y, float W, float H, const FLinearColor& Color)
{
	const FVector2D A = ToScreen(FVector2D(X, Y)), B = ToScreen(FVector2D(X + W, Y + H));
	const float X0 = FMath::RoundToFloat(A.X), Y0 = FMath::RoundToFloat(A.Y), X1 = FMath::RoundToFloat(B.X), Y1 = FMath::RoundToFloat(B.Y);
	if (X1 <= X0 || Y1 <= Y0 || Color.A <= 0.f)
	{
		return;
	}
	FCanvasTileItem Tile(FVector2D(X0, Y0), FVector2D(X1 - X0, Y1 - Y0), Color);
	Tile.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Tile);
}

void AFuryHUD::Frame(float X, float Y, float W, float H, float Thickness, const FLinearColor& Color)
{
	Rect(X, Y, W, Thickness, Color);
	Rect(X, Y + H - Thickness, W, Thickness, Color);
	Rect(X, Y + Thickness, Thickness, H - 2.f * Thickness, Color);
	Rect(X + W - Thickness, Y + Thickness, Thickness, H - 2.f * Thickness, Color);
}

void AFuryHUD::QuadGradient(FVector2D A, FVector2D B, FVector2D C, FVector2D D, const FLinearColor& CA, const FLinearColor& CB, const FLinearColor& CC, const FLinearColor& CD)
{
	A = ToScreen(A); B = ToScreen(B); C = ToScreen(C); D = ToScreen(D);
	TArray<FCanvasUVTri> Tris;
	Tris.Add(MakeTri(A, B, C, CA, CB, CC));
	Tris.Add(MakeTri(A, C, D, CA, CC, CD));
	FCanvasTriangleItem Item(Tris, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AFuryHUD::Quad(FVector2D A, FVector2D B, FVector2D C, FVector2D D, const FLinearColor& Color)
{
	QuadGradient(A, B, C, D, Color, Color, Color, Color);
}

void AFuryHUD::Slant(float X, float Y, float W, float H, float Lean, const FLinearColor& Color)
{
	Quad(FVector2D(X + Lean, Y), FVector2D(X + W + Lean, Y), FVector2D(X + W, Y + H), FVector2D(X, Y + H), Color);
}

void AFuryHUD::SlantGradient(float X, float Y, float W, float H, float Lean, const FLinearColor& Top, const FLinearColor& Bottom)
{
	QuadGradient(FVector2D(X + Lean, Y), FVector2D(X + W + Lean, Y), FVector2D(X + W, Y + H), FVector2D(X, Y + H), Top, Top, Bottom, Bottom);
}

void AFuryHUD::GradientV(float X, float Y, float W, float H, const FLinearColor& Top, const FLinearColor& Bottom)
{
	QuadGradient(FVector2D(X, Y), FVector2D(X + W, Y), FVector2D(X + W, Y + H), FVector2D(X, Y + H), Top, Top, Bottom, Bottom);
}

void AFuryHUD::GradientH(float X, float Y, float W, float H, const FLinearColor& Left, const FLinearColor& Right)
{
	QuadGradient(FVector2D(X, Y), FVector2D(X + W, Y), FVector2D(X + W, Y + H), FVector2D(X, Y + H), Left, Right, Right, Left);
}

void AFuryHUD::Line(FVector2D A, FVector2D B, float Thickness, const FLinearColor& Color)
{
	const FVector2D Dir = (B - A).GetSafeNormal();
	const FVector2D Side = FVector2D(-Dir.Y, Dir.X) * Thickness * 0.5f;
	Quad(A + Side, B + Side, B - Side, A - Side, Color);
}

void AFuryHUD::Triangle(FVector2D A, FVector2D B, FVector2D C, const FLinearColor& Color)
{
	TArray<FCanvasUVTri> Tris;
	Tris.Add(MakeTri(ToScreen(A), ToScreen(B), ToScreen(C), Color, Color, Color));
	FCanvasTriangleItem Item(Tris, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AFuryHUD::Circle(FVector2D Center, float Radius, const FLinearColor& Color, int32 Segments)
{
	TArray<FCanvasUVTri> Tris;
	Tris.Reserve(Segments);
	const FVector2D C = ToScreen(Center);
	const float R = Radius * S;
	for (int32 i = 0; i < Segments; ++i)
	{
		const float A0 = UE_TWO_PI * i / Segments, A1 = UE_TWO_PI * (i + 1) / Segments;
		Tris.Add(MakeTri(C, C + FVector2D(FMath::Cos(A0), FMath::Sin(A0)) * R, C + FVector2D(FMath::Cos(A1), FMath::Sin(A1)) * R, Color, Color, Color));
	}
	FCanvasTriangleItem Item(Tris, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AFuryHUD::Ring(FVector2D Center, float Radius, float Thickness, const FLinearColor& Color, int32 Segments, float StartFraction, float EndFraction)
{
	TArray<FCanvasUVTri> Tris;
	Tris.Reserve(Segments * 2);
	const FVector2D C = ToScreen(Center);
	const float R0 = (Radius - Thickness * 0.5f) * S, R1 = (Radius + Thickness * 0.5f) * S;
	// Fraction 0 is straight up; fractions run clockwise.
	for (int32 i = 0; i < Segments; ++i)
	{
		const float F0 = FMath::Lerp(StartFraction, EndFraction, static_cast<float>(i) / Segments);
		const float F1 = FMath::Lerp(StartFraction, EndFraction, static_cast<float>(i + 1) / Segments);
		const float A0 = UE_TWO_PI * F0 - UE_HALF_PI, A1 = UE_TWO_PI * F1 - UE_HALF_PI;
		const FVector2D D0(FMath::Cos(A0), FMath::Sin(A0)), D1(FMath::Cos(A1), FMath::Sin(A1));
		Tris.Add(MakeTri(C + D0 * R0, C + D0 * R1, C + D1 * R1, Color, Color, Color));
		Tris.Add(MakeTri(C + D0 * R0, C + D1 * R1, C + D1 * R0, Color, Color, Color));
	}
	FCanvasTriangleItem Item(Tris, GWhiteTexture);
	Item.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Item);
}

void AFuryHUD::Image(UTexture* Texture, float X, float Y, float W, float H, const FLinearColor& Tint, FVector2D UV0, FVector2D UV1)
{
	if (!Texture || !Texture->GetResource())
	{
		return;
	}
	const FVector2D A = ToScreen(FVector2D(X, Y));
	FCanvasTileItem Tile(A, Texture->GetResource(), FVector2D(W * S, H * S), UV0, UV1, Tint);
	Tile.BlendMode = SE_BLEND_Translucent;
	Canvas->DrawItem(Tile);
}

void AFuryHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas)
	{
		return;
	}
	if (!UIFont)
	{
		BuildFont();
	}
	S = FMath::Min(Canvas->SizeX / 1920.f, Canvas->SizeY / 1080.f);
	OX = (Canvas->SizeX - 1920.f * S) * 0.5f;
	OY = (Canvas->SizeY - 1080.f * S) * 0.5f;

	AFuryGameMode* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<AFuryGameMode>() : nullptr;
	AFuryDirector* Director = Mode ? Mode->Director.Get() : nullptr;
	Hud = Director;
	SharedPromptPad = FFuryInput::Get().FirstConnectedGamepad();
	if (!Director)
	{
		return;
	}
	if (Director->QuitPad != INDEX_NONE)
	{
		ScreenShade(Fade(FuryUI::Ink, 0.72f));
		Panel(570.f, 360.f, 780.f, 325.f, FuryUI::Blaze, 0.96f);
		TextShadow(TEXT("QUIT GAME?"), 960.f, 386.f, EFuryFace::BlackItalic, 82.f, FuryUI::White, EFuryAlign::Center);
		Text(Director->bPaused ? TEXT("Close the game and end this match?") : TEXT("Close 4th & Fury?"),
			960.f, 510.f, EFuryFace::SemiBold, 36.f, FuryUI::White, EFuryAlign::Center);
		Prompts(INDEX_NONE, {{FuryUI::A, TEXT("QUIT GAME")}, {FuryUI::B, TEXT("CANCEL")}}, 960.f, 601.f, 34.f);
		return;
	}
	if (Director->SettingsPad != INDEX_NONE)
	{
		DrawSettings(Director);
		return;
	}
	switch (Director->Screen)
	{
	case EFuryScreen::Viewer: DrawViewer(Director); break;
	case EFuryScreen::Title: DrawTitle(Director); break;
	case EFuryScreen::Lobby: DrawLobby(Director); break;
	case EFuryScreen::Teams: DrawTeams(Director); break;
	case EFuryScreen::Match:
		DrawMatch(Director);
		if (Director->Options.Get(EFuryOption::ShowFPS) && Director->LiveFPS > 0.f)
		{
			Rect(1610.f, 23.f, 260.f, 41.f, Fade(FuryUI::Ink, 0.88f));
			Text(FString::Printf(TEXT("%.0f FPS   /   %.1f ms"), Director->LiveFPS, 1000.f / Director->LiveFPS),
				1854.f, 27.f, EFuryFace::SemiBold, 26.f, FuryUI::White, EFuryAlign::Right);
		}
		break;
	case EFuryScreen::Final: DrawFinal(Director); break;
	}
	if (Director->Options.Get(EFuryOption::Captions) && !Director->bPaused && !Director->bViewingFilm
		&& Director->Screen != EFuryScreen::Viewer && Director->GetAudio())
	{
		const FString& Line = Director->GetAudio()->Caption();
		if (!Line.IsEmpty())
		{
			float Top = 1019.f;
			if (Director->Screen == EFuryScreen::Title) { Top = 42.f; }
			else if (Director->Screen == EFuryScreen::Teams) { Top = 732.f; }
			else if (Director->Screen == EFuryScreen::Final) { Top = 186.f; }
			const float Width = Measure(Line, EFuryFace::SemiBold, 31.f).X + 46.f;
			Rect(960.f - Width * 0.5f, Top, Width, 44.f, Fade(FuryUI::Ink, 0.96f));
			Text(Line, 960.f, Top + 2.f, EFuryFace::SemiBold, 31.f, FuryUI::White, EFuryAlign::Center);
		}
	}
}

void AFuryHUD::DrawViewer(AFuryDirector* Director)
{
	SlantGradient(40.f, 40.f, 620.f, 96.f, 26.f, FLinearColor(0.02f, 0.02f, 0.03f, 0.85f), FLinearColor(0.02f, 0.02f, 0.03f, 0.6f));
	Slant(40.f, 40.f, 14.f, 96.f, 26.f, FLinearColor(1.f, 0.35f, 0.05f));
	Text(TEXT("ANIMATION VIEWER"), 96.f, 48.f, EFuryFace::Bold, 24.f, FLinearColor(1.f, 0.6f, 0.2f), EFuryAlign::Left, 160);
	TextShadow(Director->ViewerLabel(), 92.f, 70.f, EFuryFace::BlackItalic, 58.f, FLinearColor::White);
}

// ---------------------------------------------------------------------------------------------
// Widgets
// ---------------------------------------------------------------------------------------------

float AFuryHUD::Ease(float T)
{
	T = FMath::Clamp(T, 0.f, 1.f);
	return 1.f - FMath::Pow(1.f - T, 3.f);
}

FLinearColor AFuryHUD::InkOn(const FLinearColor& Background)
{
	const float Luma = 0.2126f * Background.R + 0.7152f * Background.G + 0.0722f * Background.B;
	return Luma > 0.45f ? FuryUI::Ink : FuryUI::White;
}

bool AFuryHUD::WorldToBoard(const FVector& World, FVector2D& Out)
{
	const FVector Screen = Project(World);
	if (Screen.Z <= 0.f)
	{
		return false;
	}
	Out = FVector2D((Screen.X - OX) / S, (Screen.Y - OY) / S);
	return true;
}

void AFuryHUD::ScreenShade(FLinearColor Top, FLinearColor Bottom)
{
	const float Left = -OX / S, Above = -OY / S;
	GradientV(Left, Above, 1920.f - 2.f * Left, 1080.f - 2.f * Above, Top, Bottom);
}

void AFuryHUD::Panel(float X, float Y, float W, float H, const FLinearColor& Accent, float Alpha)
{
	GradientV(X, Y, W, H, Fade(FuryUI::Slate, Alpha), Fade(FuryUI::Ink, Alpha));
	Rect(X, Y, W, 5.f, Accent);
	Frame(X, Y, W, H, 1.5f, Fade(FuryUI::White, 0.08f));
}

void AFuryHUD::Meter(float X, float Y, float W, float H, float Fraction, const FLinearColor& Fill, const FLinearColor& Back)
{
	const float Lean = H * 0.45f;
	Slant(X, Y, W, H, Lean, Back);
	const float Amount = FMath::Clamp(Fraction, 0.f, 1.f);
	if (Amount > 0.005f)
	{
		Slant(X, Y, W * Amount, H, Lean, Fill);
	}
}

float AFuryHUD::SeatChip(int32 Seat, float X, float Y, float Height, bool bCpu)
{
	const FLinearColor Color = bCpu ? FLinearColor(0.35f, 0.37f, 0.42f) : AFuryDirector::SeatColor(Seat);
	const FString Label = bCpu ? FString(TEXT("CPU")) : FString::Printf(TEXT("P%d"), Seat + 1);
	const float Size = Height * 0.74f;
	const float Width = Measure(Label, EFuryFace::BlackItalic, Size).X + Height * 0.7f;
	Slant(X, Y, Width, Height, Height * 0.28f, Color);
	Text(Label, X + Width * 0.5f + Height * 0.14f, Y + Height * 0.06f, EFuryFace::BlackItalic, Size, InkOn(Color), EFuryAlign::Center);
	return Width + Height * 0.28f;
}

float AFuryHUD::Glyph(int32 Seat, uint8 Button, float X, float Y, float Size, bool bMeasureOnly)
{
	int32 Pad = Hud ? (Hud->QuitPad != INDEX_NONE ? Hud->QuitPad : Hud->SettingsPad) : INDEX_NONE;
	if (Pad == INDEX_NONE && Hud && Seat >= 0 && Seat < Fury::MaxSeats && Hud->Seats[Seat].bJoined && !Hud->Seats[Seat].bBot)
	{
		Pad = Hud->Seats[Seat].Pad;
	}
	if (Pad == INDEX_NONE && Seat == INDEX_NONE) { Pad = SharedPromptPad; }
	const int32 Keyboard = Pad == FFuryInput::KeyboardA || Pad == FFuryInput::KeyboardB ? Pad : INDEX_NONE;
	static const TCHAR* Keys[2][9] = {
		{ TEXT("G"), TEXT("H"), TEXT("F"), TEXT("T"), TEXT("Q"), TEXT("E"), TEXT("ESC"), TEXT("WASD"), TEXT("L SHIFT") },
		{ TEXT("K"), TEXT("L"), TEXT("J"), TEXT("I"), TEXT("U"), TEXT("O"), TEXT("ENTER"), TEXT("ARROWS"), TEXT("R SHIFT") } };
	static const TCHAR* Pads[9] = { TEXT("A"), TEXT("B"), TEXT("X"), TEXT("Y"), TEXT("LB"), TEXT("RB"), TEXT("START"), TEXT("STICK"), TEXT("LT / RT") };
	static const FLinearColor Colors[4] = { FLinearColor(0.2f, 0.82f, 0.3f), FLinearColor(0.92f, 0.2f, 0.17f), FLinearColor(0.16f, 0.46f, 1.f), FLinearColor(1.f, 0.78f, 0.08f) };
	const uint8 Index = FMath::Min<uint8>(Button, FuryUI::Turbo);
	const FString Label = Keyboard != INDEX_NONE ? Keys[Keyboard][Index] : Pads[Index];
	const bool bRound = Keyboard == INDEX_NONE && Index < 4;
	if (bRound)
	{
		if (bMeasureOnly) { return Size; }
		const FVector2D Centre(X + Size * 0.5f, Y + Size * 0.5f);
		Circle(Centre, Size * 0.5f, FuryUI::Ink, 24);
		if (Pad >= FFuryInput::FirstGamepad)
		{
			const FName Symbol = FFuryInput::Get().Pad(Pad).FaceSymbols[Index];
			if (!Symbol.IsNone())
			{
				if (!ControllerIcons.Contains(Symbol)) { ControllerIcons.Add(Symbol, FFuryInput::MakeFaceTexture(Symbol)); }
				UTexture* Icon = ControllerIcons.FindRef(Symbol);
				if (Icon && Icon->GetResource())
				{
					Image(Icon, X + Size * 0.06f, Y + Size * 0.06f, Size * 0.88f, Size * 0.88f, FuryUI::White);
					return Size;
				}
			}
		}
		Circle(Centre, Size * 0.43f, Colors[Index], 24);
		Text(Label, Centre.X, Y + Size * 0.1f, EFuryFace::Black, Size * 0.66f, FuryUI::Ink, EFuryAlign::Center);
		return Size;
	}
	const float TextSize = Size * 0.6f;
	const float Width = FMath::Max(Size, Measure(Label, EFuryFace::Bold, TextSize).X + Size * 0.5f);
	if (bMeasureOnly) { return Width; }
	Rect(X, Y, Width, Size, FuryUI::Ink);
	Rect(X + 2.f, Y + 2.f, Width - 4.f, Size - 6.f, FLinearColor(0.86f, 0.88f, 0.9f));
	Text(Label, X + Width * 0.5f, Y + Size * 0.1f, EFuryFace::Bold, TextSize, FuryUI::Ink, EFuryAlign::Center);
	return Width;
}

void AFuryHUD::Prompts(int32 Seat, std::initializer_list<TPair<uint8, const TCHAR*>> Items, float CenterX, float Y, float Size)
{
	// Measure first so the whole row can be centred.
	const float Gap = Size * 1.1f, Pad = Size * 0.3f;
	float Total = 0.f;
	for (const TPair<uint8, const TCHAR*>& Item : Items)
	{
		Total += Glyph(Seat, Item.Key, 0.f, 0.f, Size, true) + Pad + Measure(Item.Value, EFuryFace::SemiBold, Size * 0.86f, 60).X + Gap;
	}
	float X = CenterX - (Total - Gap) * 0.5f;
	for (const TPair<uint8, const TCHAR*>& Item : Items)
	{
		X += Glyph(Seat, Item.Key, X, Y, Size) + Pad;
		X += TextShadow(Item.Value, X, Y + Size * 0.04f, EFuryFace::SemiBold, Size * 0.86f, FuryUI::White, EFuryAlign::Left, 60, 2.f) + Gap;
	}
}
