#pragma once

#include "CoreMinimal.h"
#include "Engine/GameViewportClient.h"
#include "FuryInput.generated.h"

class UTexture2D;

/** The buttons the game understands, named after an Xbox-style pad. */
enum class EFuryButton : uint8
{
	A, B, X, Y, LB, RB, LT, RT, Start, Back, Up, Down, Left, Right,
	Count
};

enum class EFuryPadKind : uint8 { None, Keyboard, Gamepad, Bot };

/**
 * One input device as the game sees it: a gamepad, one half of the keyboard, or a scripted bot.
 * Stick.X is right-positive, Stick.Y is up-positive.
 */
struct FFuryPad
{
	EFuryPadKind Kind = EFuryPadKind::None;
	bool bConnected = false;
	FString Label;
	FName FaceSymbols[4];

	FVector2D Stick = FVector2D::ZeroVector;
	bool Down[static_cast<int32>(EFuryButton::Count)] = {};
	bool Pressed[static_cast<int32>(EFuryButton::Count)] = {};
	bool Released[static_cast<int32>(EFuryButton::Count)] = {};

	// Menu navigation: one step per push, with auto-repeat while held.
	int32 NavX = 0, NavY = 0;

	bool IsDown(EFuryButton B) const { return Down[static_cast<int32>(B)]; }
	bool WasPressed(EFuryButton B) const { return Pressed[static_cast<int32>(B)]; }
	bool WasReleased(EFuryButton B) const { return Released[static_cast<int32>(B)]; }
	bool AnyPressed() const;
	bool Turbo() const { return IsDown(EFuryButton::RT) || IsDown(EFuryButton::LT); }

private:
	friend class FFuryInput;
	void RecordButton(EFuryButton Button, bool bHeld);
	bool PendingPress[static_cast<int32>(EFuryButton::Count)] = {};
	bool PendingRelease[static_cast<int32>(EFuryButton::Count)] = {};
	bool Raw[static_cast<int32>(EFuryButton::Count)] = {};
	FVector2D RawStick = FVector2D::ZeroVector;
	float NavHold[2] = {};
	int32 NavDir[2] = {};
	uint64 NativeId = 0;
	FString NativeName;
	double RefreshSymbolsAt = 0.0;
	bool bSeen = false;
};

/**
 * Collects input from every device into pads.
 *
 * Sources: the keyboard (split into two pads), Unreal's gamepad events (any platform), and on
 * macOS the GameController framework directly, because Unreal's own Apple layer only reports
 * four controllers and this game seats eight.
 */
class FFuryInput
{
public:
	static constexpr int32 MaxPads = 16;
	static constexpr int32 KeyboardA = 0;
	static constexpr int32 KeyboardB = 1;
	static constexpr int32 FirstGamepad = 2;

	static FFuryInput& Get();

	/** Called once per frame before the game logic reads the pads. */
	void Tick(float DeltaTime);

	FFuryPad& Pad(int32 Index) { return Pads[Index]; }
	const FFuryPad& Pad(int32 Index) const { return Pads[Index]; }
	int32 NumConnectedGamepads() const;
	int32 FirstConnectedGamepad() const;
	static UTexture2D* MakeFaceTexture(FName Symbol);

	/** Scripted input (tests, attract mode): claims a pad slot that the game treats like a device. */
	int32 AddBot(const FString& Label);
	void SetBot(int32 Index, FVector2D Stick, std::initializer_list<EFuryButton> Held);

	// Fed by the viewport client.
	bool HandleKey(const FInputKeyEventArgs& Args);
	bool HandleAxis(const FInputKeyEventArgs& Args);
	void ReleaseKeyboard();

private:
	friend class FFuryReconnectTest;
	FFuryInput();
	int32 PadForDevice(int32 DeviceId);
	int32 PadForNative(uint64 NativeId, const FString& Name);
	void PollNative();

	FFuryPad Pads[MaxPads];
	TMap<int32, int32> DevicePads;
	TSet<FKey> HeldKeys;
	bool bNativeGamepads = false;
};

/** Routes raw key and axis events from every device into FFuryInput. */
UCLASS()
class UFuryViewportClient : public UGameViewportClient
{
	GENERATED_BODY()

public:
	virtual bool InputKey(const FInputKeyEventArgs& EventArgs) override;
	virtual bool InputAxis(const FInputKeyEventArgs& EventArgs) override;
	virtual void LostFocus(FViewport* Viewport) override;
};
