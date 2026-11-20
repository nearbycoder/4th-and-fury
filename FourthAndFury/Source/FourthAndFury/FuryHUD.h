#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "GameFramework/HUD.h"
#include "FuryHUD.generated.h"

class AFuryDirector;
class UFont;
class UTexture;

enum class EFuryFace : uint8 { Medium, SemiBold, Bold, ExtraBold, Black, BoldItalic, ExtraBoldItalic, BlackItalic, Anton, Graduate, Count };
enum class EFuryAlign : uint8 { Left, Center, Right };

/**
 * The whole interface is drawn straight onto the canvas from a small kit.
 *
 * Layout is authored on a 1920 x 1080 board; the kit scales it to the window and letterboxes
 * when the window is not 16:9. Kit functions take board coordinates.
 */
UCLASS()
class AFuryHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	// --- Kit: type ---
	FSlateFontInfo Font(EFuryFace Face, float Size, int32 Spacing = 0) const;
	FVector2D Measure(const FString& Str, EFuryFace Face, float Size, int32 Spacing = 0) const;
	/** Draws text with its top-left / top-centre / top-right at (X, Y). Returns the width. */
	float Text(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, EFuryAlign Align = EFuryAlign::Left, int32 Spacing = 0);
	/** Text with a dark offset shadow. */
	float TextShadow(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, EFuryAlign Align = EFuryAlign::Left, int32 Spacing = 0, float Offset = 3.f);
	/** Text with a solid outline (stamped copies), for titles over busy backgrounds. */
	float TextOutline(const FString& Str, float X, float Y, EFuryFace Face, float Size, const FLinearColor& Color, const FLinearColor& Outline, float Thickness, EFuryAlign Align = EFuryAlign::Left, int32 Spacing = 0);

	// --- Kit: shapes ---
	void Rect(float X, float Y, float W, float H, const FLinearColor& Color);
	void Frame(float X, float Y, float W, float H, float Thickness, const FLinearColor& Color);
	void Quad(FVector2D A, FVector2D B, FVector2D C, FVector2D D, const FLinearColor& Color);
	void QuadGradient(FVector2D A, FVector2D B, FVector2D C, FVector2D D, const FLinearColor& CA, const FLinearColor& CB, const FLinearColor& CC, const FLinearColor& CD);
	/** A parallelogram: the top edge is shifted right by Lean. */
	void Slant(float X, float Y, float W, float H, float Lean, const FLinearColor& Color);
	void SlantGradient(float X, float Y, float W, float H, float Lean, const FLinearColor& Top, const FLinearColor& Bottom);
	void GradientV(float X, float Y, float W, float H, const FLinearColor& Top, const FLinearColor& Bottom);
	void ScreenShade(FLinearColor Top, FLinearColor Bottom);
	void ScreenShade(FLinearColor Solid) { ScreenShade(Solid, Solid); }
	void GradientH(float X, float Y, float W, float H, const FLinearColor& Left, const FLinearColor& Right);
	void Line(FVector2D A, FVector2D B, float Thickness, const FLinearColor& Color);
	void Circle(FVector2D Center, float Radius, const FLinearColor& Color, int32 Segments = 28);
	void Ring(FVector2D Center, float Radius, float Thickness, const FLinearColor& Color, int32 Segments = 32, float StartFraction = 0.f, float EndFraction = 1.f);
	void Triangle(FVector2D A, FVector2D B, FVector2D C, const FLinearColor& Color);
	void Image(UTexture* Texture, float X, float Y, float W, float H, const FLinearColor& Tint = FLinearColor::White, FVector2D UV0 = FVector2D(0, 0), FVector2D UV1 = FVector2D(1, 1));

	float BoardScale() const { return S; }
	float Now() const;

protected:
	void BuildFont();
	FVector2D ToScreen(FVector2D Board) const { return FVector2D(OX + Board.X * S, OY + Board.Y * S); }
	void Stamp(const FString& Str, float ScreenX, float ScreenY, const FSlateFontInfo& FontInfo, const FLinearColor& Color);
	void DrawViewer(AFuryDirector* Director);

	// --- Widgets shared by every screen (FuryHUD.cpp) ---
	/** A dark glass panel with a coloured edge. */
	void Panel(float X, float Y, float W, float H, const FLinearColor& Accent, float Alpha = 0.86f);
	/** A round controller-button glyph (or the matching key cap for keyboard players). Returns its width. */
	float Glyph(int32 Seat, uint8 Button, float X, float Y, float Size, bool bMeasureOnly = false);
	/** "P3" in the seat's colour. Returns its width. */
	float SeatChip(int32 Seat, float X, float Y, float Height, bool bCpu = false);
	/** A row of prompts: glyph + label pairs, centred on X. */
	void Prompts(int32 Seat, std::initializer_list<TPair<uint8, const TCHAR*>> Items, float CenterX, float Y, float Size = 26.f);
	void Meter(float X, float Y, float W, float H, float Fraction, const FLinearColor& Fill, const FLinearColor& Back);
	/** Where a point in the world lands on the board, or false if it is behind the camera. */
	bool WorldToBoard(const FVector& World, FVector2D& Out);
	static FLinearColor Fade(const FLinearColor& C, float Alpha) { return FLinearColor(C.R, C.G, C.B, C.A * Alpha); }
	static FLinearColor InkOn(const FLinearColor& Background);
	static float Ease(float T);

	// --- Menus (FuryHUDMenus.cpp) ---
	void DrawTitle(AFuryDirector* Director);
	void DrawLobby(AFuryDirector* Director);
	void DrawTeams(AFuryDirector* Director);
	void DrawFinal(AFuryDirector* Director);
	void DrawPause(AFuryDirector* Director);
	void DrawFieldGuide(AFuryDirector* Director);
	void DrawFilm(AFuryDirector* Director);
	void DrawSoloHints(AFuryDirector* Director);
	void DrawSettings(AFuryDirector* Director);
	void DrawTeamCard(AFuryDirector* Director, int32 Side, float X, float Y, float W);

	// --- The match (FuryHUDMatch.cpp) ---
	void DrawMatch(AFuryDirector* Director);
	void DrawScorebug(AFuryDirector* Director);
	void DrawBanner(AFuryDirector* Director);
	void DrawPlaySelect(AFuryDirector* Director);
	void DrawPickPanel(AFuryDirector* Director, int32 Team, float X, float Y, float W, float H);
	void DrawOffenseCard(const struct FFuryOffPlay& Play, bool bFlip, float X, float Y, float W, float H, const FLinearColor& Accent);
	void DrawDefenseCard(const struct FFuryDefPlay& Play, bool bFlip, float X, float Y, float W, float H, const FLinearColor& Accent);
	void DrawPatSelect(AFuryDirector* Director);
	void DrawFieldTags(AFuryDirector* Director);
	void DrawRoutes(AFuryDirector* Director, int32 Seat);
	void DrawKickMeter(AFuryDirector* Director);
	void DrawTurbo(AFuryDirector* Director);
	void DrawResult(AFuryDirector* Director);
	void DrawBoard(AFuryDirector* Director);

	UPROPERTY()
	TMap<FName, TObjectPtr<UTexture>> ControllerIcons;
	int32 SharedPromptPad = INDEX_NONE;
	float BoardTimer = 0.f;
	FString LastBoardContent;

	/** The director being drawn this frame (set at the top of DrawHUD). */
	AFuryDirector* Hud = nullptr;

	UPROPERTY()
	TObjectPtr<UFont> UIFont;

	float S = 1.f, OX = 0.f, OY = 0.f;
};
