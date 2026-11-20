#include "FuryInput.h"

#include "FuryTypes.h"
#include "InputCoreTypes.h"
#include "InputKeyEventArgs.h"

namespace
{
	constexpr float StickDeadZone = 0.22f;
	constexpr float NavThreshold = 0.55f;
	constexpr float NavFirstRepeat = 0.38f;
	constexpr float NavRepeat = 0.13f;

	struct FKeyBinding { FKey Key; int32 Pad; EFuryButton Button; };
	struct FKeyDirection { FKey Key; int32 Pad; FVector2D Dir; };

	const TArray<FKeyBinding>& KeyButtons()
	{
		static const TArray<FKeyBinding> Bindings = {
			// Keyboard A: WASD to move, T/F/G/H as the Y/X/A/B diamond.
			{ EKeys::G, FFuryInput::KeyboardA, EFuryButton::A }, { EKeys::SpaceBar, FFuryInput::KeyboardA, EFuryButton::A },
			{ EKeys::H, FFuryInput::KeyboardA, EFuryButton::B }, { EKeys::F, FFuryInput::KeyboardA, EFuryButton::X },
			{ EKeys::T, FFuryInput::KeyboardA, EFuryButton::Y }, { EKeys::LeftShift, FFuryInput::KeyboardA, EFuryButton::RT },
			{ EKeys::Q, FFuryInput::KeyboardA, EFuryButton::LB }, { EKeys::E, FFuryInput::KeyboardA, EFuryButton::RB },
			{ EKeys::Escape, FFuryInput::KeyboardA, EFuryButton::Start }, { EKeys::Tab, FFuryInput::KeyboardA, EFuryButton::Back },
			// Keyboard B: arrows to move, I/J/K/L as the Y/X/A/B diamond.
			{ EKeys::K, FFuryInput::KeyboardB, EFuryButton::A }, { EKeys::L, FFuryInput::KeyboardB, EFuryButton::B },
			{ EKeys::J, FFuryInput::KeyboardB, EFuryButton::X }, { EKeys::I, FFuryInput::KeyboardB, EFuryButton::Y },
			{ EKeys::RightShift, FFuryInput::KeyboardB, EFuryButton::RT }, { EKeys::U, FFuryInput::KeyboardB, EFuryButton::LB },
			{ EKeys::O, FFuryInput::KeyboardB, EFuryButton::RB }, { EKeys::Enter, FFuryInput::KeyboardB, EFuryButton::Start },
			{ EKeys::BackSpace, FFuryInput::KeyboardB, EFuryButton::Back },
		};
		return Bindings;
	}

	const TArray<FKeyDirection>& KeyDirections()
	{
		static const TArray<FKeyDirection> Bindings = {
			{ EKeys::W, FFuryInput::KeyboardA, FVector2D(0, 1) }, { EKeys::S, FFuryInput::KeyboardA, FVector2D(0, -1) },
			{ EKeys::A, FFuryInput::KeyboardA, FVector2D(-1, 0) }, { EKeys::D, FFuryInput::KeyboardA, FVector2D(1, 0) },
			{ EKeys::Up, FFuryInput::KeyboardB, FVector2D(0, 1) }, { EKeys::Down, FFuryInput::KeyboardB, FVector2D(0, -1) },
			{ EKeys::Left, FFuryInput::KeyboardB, FVector2D(-1, 0) }, { EKeys::Right, FFuryInput::KeyboardB, FVector2D(1, 0) },
		};
		return Bindings;
	}

	bool GamepadButton(const FKey& Key, EFuryButton& Out)
	{
		static const TMap<FKey, EFuryButton> Map = {
			{ EKeys::Gamepad_FaceButton_Bottom, EFuryButton::A }, { EKeys::Gamepad_FaceButton_Right, EFuryButton::B },
			{ EKeys::Gamepad_FaceButton_Left, EFuryButton::X }, { EKeys::Gamepad_FaceButton_Top, EFuryButton::Y },
			{ EKeys::Gamepad_LeftShoulder, EFuryButton::LB }, { EKeys::Gamepad_RightShoulder, EFuryButton::RB },
			{ EKeys::Gamepad_LeftTrigger, EFuryButton::LT }, { EKeys::Gamepad_RightTrigger, EFuryButton::RT },
			{ EKeys::Gamepad_Special_Right, EFuryButton::Start }, { EKeys::Gamepad_Special_Left, EFuryButton::Back },
			{ EKeys::Gamepad_DPad_Up, EFuryButton::Up }, { EKeys::Gamepad_DPad_Down, EFuryButton::Down },
			{ EKeys::Gamepad_DPad_Left, EFuryButton::Left }, { EKeys::Gamepad_DPad_Right, EFuryButton::Right },
		};
		if (const EFuryButton* Found = Map.Find(Key))
		{
			Out = *Found;
			return true;
		}
		return false;
	}
}

bool FFuryPad::AnyPressed() const
{
	for (const bool bPressed : Pressed)
	{
		if (bPressed)
		{
			return true;
		}
	}
	return false;
}

FFuryInput& FFuryInput::Get()
{
	static FFuryInput Instance;
	return Instance;
}

FFuryInput::FFuryInput()
{
	Pads[KeyboardA].Kind = EFuryPadKind::Keyboard;
	Pads[KeyboardA].bConnected = true;
	Pads[KeyboardA].Label = TEXT("KEYS  WASD");
	Pads[KeyboardB].Kind = EFuryPadKind::Keyboard;
	Pads[KeyboardB].bConnected = true;
	Pads[KeyboardB].Label = TEXT("KEYS  ARROWS");
#if PLATFORM_MAC
	bNativeGamepads = true;
#endif
}

int32 FFuryInput::NumConnectedGamepads() const
{
	int32 Count = 0;
	for (const FFuryPad& P : Pads)
	{
		Count += (P.Kind == EFuryPadKind::Gamepad && P.bConnected) ? 1 : 0;
	}
	return Count;
}

int32 FFuryInput::FirstConnectedGamepad() const
{
	for (int32 i = FirstGamepad; i < MaxPads; ++i)
	{
		if (Pads[i].Kind == EFuryPadKind::Gamepad && Pads[i].bConnected) { return i; }
	}
	return INDEX_NONE;
}

int32 FFuryInput::PadForDevice(int32 DeviceId)
{
	if (const int32* Found = DevicePads.Find(DeviceId))
	{
		return *Found;
	}
	for (int32 i = FirstGamepad; i < MaxPads; ++i)
	{
		if (Pads[i].Kind == EFuryPadKind::None)
		{
			Pads[i] = FFuryPad();
			Pads[i].Kind = EFuryPadKind::Gamepad;
			Pads[i].bConnected = true;
			Pads[i].Label = FString::Printf(TEXT("PAD %d"), NumConnectedGamepads());
			DevicePads.Add(DeviceId, i);
			UE_LOG(LogFury, Log, TEXT("Input: gamepad device %d -> pad slot %d"), DeviceId, i);
			return i;
		}
	}
	return INDEX_NONE;
}

int32 FFuryInput::PadForNative(uint64 NativeId, const FString& Name)
{
	// macOS can create a new GCController on reconnect. Prefer its previous model when
	// multiple seats are open. A different replacement pad can still take over a vacant seat.
	int32 Vacant = INDEX_NONE;
	for (int32 i = FirstGamepad; i < MaxPads; ++i)
	{
		const FFuryPad& P = Pads[i];
		if (P.Kind != EFuryPadKind::Gamepad) { continue; }
		if (P.NativeId == NativeId && P.NativeName == Name) { return i; }
		if (!P.bConnected && (Vacant == INDEX_NONE || (P.NativeName == Name && Pads[Vacant].NativeName != Name)))
		{
			Vacant = i;
		}
	}
	if (Vacant != INDEX_NONE)
	{
		FFuryPad& P = Pads[Vacant];
		P.bConnected = true;
		P.NativeId = NativeId;
		P.RefreshSymbolsAt = 0.0;
		P.NativeName = Name;
		UE_LOG(LogFury, Log, TEXT("Input: controller \"%s\" reconnected -> pad slot %d"), *Name, Vacant);
		return Vacant;
	}
	for (int32 i = FirstGamepad; i < MaxPads; ++i)
	{
		if (Pads[i].Kind == EFuryPadKind::None)
		{
			Pads[i] = FFuryPad();
			Pads[i].Kind = EFuryPadKind::Gamepad;
			Pads[i].bConnected = true;
			Pads[i].NativeId = NativeId;
			Pads[i].NativeName = Name;
			Pads[i].Label = FString::Printf(TEXT("PAD %d"), NumConnectedGamepads());
			UE_LOG(LogFury, Log, TEXT("Input: controller \"%s\" -> pad slot %d"), *Name, i);
			return i;
		}
	}
	return INDEX_NONE;
}

int32 FFuryInput::AddBot(const FString& Label)
{
	for (int32 i = FirstGamepad; i < MaxPads; ++i)
	{
		if (Pads[i].Kind == EFuryPadKind::None)
		{
			Pads[i] = FFuryPad();
			Pads[i].Kind = EFuryPadKind::Bot;
			Pads[i].bConnected = true;
			Pads[i].Label = Label;
			return i;
		}
	}
	return INDEX_NONE;
}

void FFuryInput::SetBot(int32 Index, FVector2D Stick, std::initializer_list<EFuryButton> Held)
{
	if (Index < 0 || Index >= MaxPads || Pads[Index].Kind != EFuryPadKind::Bot)
	{
		return;
	}
	FFuryPad& P = Pads[Index];
	P.RawStick = Stick;
	FMemory::Memzero(P.Raw);
	for (const EFuryButton B : Held)
	{
		P.Raw[static_cast<int32>(B)] = true;
	}
}

void FFuryPad::RecordButton(EFuryButton Button, bool bHeld)
{
	const int32 Index = static_cast<int32>(Button);
	if (Raw[Index] == bHeld) { return; }
	Raw[Index] = bHeld;
	if (bHeld) { PendingPress[Index] = true; }
	else { PendingRelease[Index] = true; }
}

bool FFuryInput::HandleKey(const FInputKeyEventArgs& Args)
{
	if (Args.Event != IE_Pressed && Args.Event != IE_Released)
	{
		return false;
	}
	const bool bDown = Args.Event == IE_Pressed;

	if (Args.Key.IsGamepadKey())
	{
		EFuryButton Button;
		if (bNativeGamepads || !GamepadButton(Args.Key, Button))
		{
			return false;
		}
		const int32 Index = PadForDevice(Args.InputDevice.GetId());
		if (Index != INDEX_NONE)
		{
			Pads[Index].RecordButton(Button, bDown);
		}
		return true;
	}

	if (bDown) { HeldKeys.Add(Args.Key); }
	else { HeldKeys.Remove(Args.Key); }
	bool bHandled = false;
	for (const FKeyBinding& Binding : KeyButtons())
	{
		if (Binding.Key == Args.Key)
		{
			const bool bStillHeld = bDown || KeyButtons().ContainsByPredicate([&](const FKeyBinding& Other)
			{
				return Other.Pad == Binding.Pad && Other.Button == Binding.Button && HeldKeys.Contains(Other.Key);
			});
			Pads[Binding.Pad].RecordButton(Binding.Button, bStillHeld);
			bHandled = true;
		}
	}
	for (const FKeyDirection& Binding : KeyDirections())
	{
		if (Binding.Key == Args.Key)
		{
			// Track each direction key as a hidden d-pad button so opposite keys cancel cleanly.
			const EFuryButton Button = Binding.Dir.Y > 0 ? EFuryButton::Up : Binding.Dir.Y < 0 ? EFuryButton::Down : Binding.Dir.X < 0 ? EFuryButton::Left : EFuryButton::Right;
			Pads[Binding.Pad].RecordButton(Button, bDown);
			bHandled = true;
		}
	}
	return bHandled;
}

void FFuryInput::ReleaseKeyboard()
{
	HeldKeys.Reset();
	for (int32 i : { KeyboardA, KeyboardB })
	{
		FMemory::Memzero(Pads[i].Raw);
		FMemory::Memzero(Pads[i].PendingPress);
		FMemory::Memzero(Pads[i].PendingRelease);
	}
}

bool FFuryInput::HandleAxis(const FInputKeyEventArgs& Args)
{
	if (!Args.Key.IsGamepadKey() || bNativeGamepads)
	{
		return false;
	}
	const bool bStick = Args.Key == EKeys::Gamepad_LeftX || Args.Key == EKeys::Gamepad_LeftY;
	const bool bTrigger = Args.Key == EKeys::Gamepad_LeftTriggerAxis || Args.Key == EKeys::Gamepad_RightTriggerAxis;
	if (!bStick && !bTrigger)
	{
		return false;
	}
	const int32 Index = PadForDevice(Args.InputDevice.GetId());
	if (Index == INDEX_NONE)
	{
		return false;
	}
	FFuryPad& P = Pads[Index];
	if (Args.Key == EKeys::Gamepad_LeftX)
	{
		P.RawStick.X = Args.AmountDepressed;
	}
	else if (Args.Key == EKeys::Gamepad_LeftY)
	{
		P.RawStick.Y = Args.AmountDepressed;
	}
	else if (Args.Key == EKeys::Gamepad_LeftTriggerAxis)
	{
		P.Raw[static_cast<int32>(EFuryButton::LT)] = Args.AmountDepressed > 0.35f;
	}
	else
	{
		P.Raw[static_cast<int32>(EFuryButton::RT)] = Args.AmountDepressed > 0.35f;
	}
	return true;
}

void FFuryInput::Tick(float DeltaTime)
{
	if (bNativeGamepads)
	{
		PollNative();
	}

	for (FFuryPad& P : Pads)
	{
		if (P.Kind == EFuryPadKind::None)
		{
			continue;
		}
		const int32 Count = static_cast<int32>(EFuryButton::Count);
		for (int32 i = 0; i < Count; ++i)
		{
			P.Pressed[i] = P.PendingPress[i] || (P.Raw[i] && !P.Down[i]);
			P.Released[i] = P.PendingRelease[i] || (!P.Raw[i] && P.Down[i]);
			P.PendingPress[i] = P.PendingRelease[i] = false;
			P.Down[i] = P.Raw[i];
		}

		// Analog stick with a radial dead zone, plus the digital directions (d-pad / keys).
		FVector2D Stick = P.RawStick;
		const float Size = Stick.Size();
		Stick = Size > StickDeadZone ? Stick / Size * FMath::Min(1.f, (Size - StickDeadZone) / (1.f - StickDeadZone)) : FVector2D::ZeroVector;
		FVector2D Digital(
			(P.Down[static_cast<int32>(EFuryButton::Right)] ? 1.f : 0.f) - (P.Down[static_cast<int32>(EFuryButton::Left)] ? 1.f : 0.f),
			(P.Down[static_cast<int32>(EFuryButton::Up)] ? 1.f : 0.f) - (P.Down[static_cast<int32>(EFuryButton::Down)] ? 1.f : 0.f));
		if (!Digital.IsNearlyZero())
		{
			Stick = Digital.GetSafeNormal();
		}
		P.Stick = Stick;

		// Menu steps with auto-repeat.
		const float Axis[2] = { Stick.X, Stick.Y };
		const int32 Tap[2] = {
			int32(P.WasPressed(EFuryButton::Right)) - int32(P.WasPressed(EFuryButton::Left)),
			int32(P.WasPressed(EFuryButton::Up)) - int32(P.WasPressed(EFuryButton::Down))
		};
		const bool Opposed[2] = {
			P.IsDown(EFuryButton::Right) && P.IsDown(EFuryButton::Left),
			P.IsDown(EFuryButton::Up) && P.IsDown(EFuryButton::Down)
		};
		int32* Nav[2] = { &P.NavX, &P.NavY };
		for (int32 a = 0; a < 2; ++a)
		{
			const int32 Dir = Axis[a] > NavThreshold ? 1 : Axis[a] < -NavThreshold ? -1 : 0;
			*Nav[a] = Dir == 0 && !Opposed[a] ? Tap[a] : 0;
			if (Dir == 0)
			{
				P.NavDir[a] = 0;
				P.NavHold[a] = 0.f;
			}
			else if (Dir != P.NavDir[a] || Dir == Tap[a])
			{
				P.NavDir[a] = Dir;
				P.NavHold[a] = NavFirstRepeat;
				*Nav[a] = Dir;
			}
			else
			{
				P.NavHold[a] -= DeltaTime;
				if (P.NavHold[a] <= 0.f)
				{
					P.NavHold[a] = NavRepeat;
					*Nav[a] = Dir;
				}
			}
		}
	}
}

#if !PLATFORM_MAC
UTexture2D* FFuryInput::MakeFaceTexture(FName) { return nullptr; }

void FFuryInput::PollNative()
{
}
#endif

bool UFuryViewportClient::InputKey(const FInputKeyEventArgs& EventArgs)
{
	const bool bHandled = FFuryInput::Get().HandleKey(EventArgs);
	// Let the engine see everything too (console key, screenshots, window shortcuts).
	return Super::InputKey(EventArgs) || bHandled;
}

bool UFuryViewportClient::InputAxis(const FInputKeyEventArgs& EventArgs)
{
	const bool bHandled = FFuryInput::Get().HandleAxis(EventArgs);
	return Super::InputAxis(EventArgs) || bHandled;
}

void UFuryViewportClient::LostFocus(FViewport* Viewport)
{
	FFuryInput::Get().ReleaseKeyboard();
	Super::LostFocus(Viewport);
}
