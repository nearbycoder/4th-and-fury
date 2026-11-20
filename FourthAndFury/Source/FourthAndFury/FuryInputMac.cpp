#include "FuryInput.h"

#if PLATFORM_MAC

#include "FuryTypes.h"
#include "Engine/Texture2D.h"

#include "Mac/MacSystemIncludes.h"   // imports Cocoa with the workarounds Unreal's types need
#include <GameController/GameController.h>

UTexture2D* FFuryInput::MakeFaceTexture(FName Symbol)
{
	if (Symbol.IsNone()) { return nullptr; }
	@autoreleasepool
	{
		NSImage* Icon = [NSImage imageWithSystemSymbolName:Symbol.ToString().GetNSString() accessibilityDescription:nil];
		if (!Icon) { return nullptr; }
		Icon = [Icon imageWithSymbolConfiguration:[NSImageSymbolConfiguration configurationWithPointSize:80 weight:NSFontWeightSemibold]];
		CGImageRef Source = [Icon CGImageForProposedRect:nullptr context:nil hints:nil];
		if (!Source || !CGImageGetWidth(Source) || !CGImageGetHeight(Source)) { return nullptr; }
		constexpr int32 Size = 96;
		TArray<uint8> Mask;
		Mask.SetNumZeroed(Size * Size);
		CGContextRef Context = CGBitmapContextCreate(Mask.GetData(), Size, Size, 8, Size, nullptr, kCGImageAlphaOnly);
		if (!Context) { return nullptr; }
		const CGFloat Scale = CGFloat(Size) / FMath::Max(CGImageGetWidth(Source), CGImageGetHeight(Source));
		const CGFloat W = CGImageGetWidth(Source) * Scale, H = CGImageGetHeight(Source) * Scale;
		CGContextDrawImage(Context, CGRectMake((Size - W) * 0.5, (Size - H) * 0.5, W, H), Source);
		CGContextRelease(Context);
		TArray64<uint8> Pixels;
		Pixels.Init(255, Size * Size * 4);
		for (int32 i = 0; i < Mask.Num(); ++i) { Pixels[i * 4 + 3] = Mask[i]; }
		UTexture2D* Texture = UTexture2D::CreateTransient(Size, Size, PF_B8G8R8A8, NAME_None, Pixels);
		if (Texture) { Texture->UpdateResource(); }
		return Texture;
	}
}

/**
 * Reads every connected controller straight from Apple's GameController framework.
 *
 * Unreal's Apple controller layer keeps a fixed array of four controllers, so pads five to eight
 * never produce engine input events. Polling the framework ourselves has no such limit, and it
 * covers Xbox, PlayStation, Switch Pro and MFi pads alike.
 */
void FFuryInput::PollNative()
{
	@autoreleasepool
	{
		for (int32 i = FirstGamepad; i < MaxPads; ++i)
		{
			if (Pads[i].Kind == EFuryPadKind::Gamepad)
			{
				Pads[i].bSeen = false;
			}
		}

		const double Now = FPlatformTime::Seconds();
		NSArray<GCController*>* Controllers = [GCController controllers];
		for (GCController* Controller in Controllers)
		{
			GCExtendedGamepad* Gamepad = Controller.extendedGamepad;
			if (Gamepad == nil)
			{
				continue;
			}
			const FString Name = Controller.vendorName != nil ? FString(Controller.vendorName) : FString(TEXT("Controller"));
			const int32 Index = PadForNative(static_cast<uint64>(reinterpret_cast<uintptr_t>(Controller)), Name);
			if (Index == INDEX_NONE)
			{
				continue;
			}
			FFuryPad& P = Pads[Index];
			// Apple supplies the physical marking after system button remapping.
			// Refresh occasionally so changing the mapping during a match updates its prompts.
			if (!P.bConnected || Now >= P.RefreshSymbolsAt)
			{
				GCControllerButtonInput* Face[] = {Gamepad.buttonA, Gamepad.buttonB, Gamepad.buttonX, Gamepad.buttonY};
				for (int32 i = 0; i < 4; ++i)
				{
					NSString* Symbol = Face[i].sfSymbolsName;
					P.FaceSymbols[i] = Symbol ? FName(*FString(Symbol)) : NAME_None;
				}
				P.RefreshSymbolsAt = Now + 1.0;
			}
			P.bSeen = true;
			P.bConnected = true;
			P.RawStick = FVector2D(Gamepad.leftThumbstick.xAxis.value, Gamepad.leftThumbstick.yAxis.value);
			auto Set = [&P](EFuryButton Button, bool bDown) { P.Raw[static_cast<int32>(Button)] = bDown; };
			Set(EFuryButton::A, Gamepad.buttonA.isPressed);
			Set(EFuryButton::B, Gamepad.buttonB.isPressed);
			Set(EFuryButton::X, Gamepad.buttonX.isPressed);
			Set(EFuryButton::Y, Gamepad.buttonY.isPressed);
			Set(EFuryButton::LB, Gamepad.leftShoulder.isPressed);
			Set(EFuryButton::RB, Gamepad.rightShoulder.isPressed);
			Set(EFuryButton::LT, Gamepad.leftTrigger.value > 0.35f);
			Set(EFuryButton::RT, Gamepad.rightTrigger.value > 0.35f);
			Set(EFuryButton::Start, Gamepad.buttonMenu.isPressed);
			Set(EFuryButton::Back, Gamepad.buttonOptions != nil && Gamepad.buttonOptions.isPressed);
			Set(EFuryButton::Up, Gamepad.dpad.up.isPressed);
			Set(EFuryButton::Down, Gamepad.dpad.down.isPressed);
			Set(EFuryButton::Left, Gamepad.dpad.left.isPressed);
			Set(EFuryButton::Right, Gamepad.dpad.right.isPressed);
		}

		// A pad that vanished releases everything; its slot stays reserved so a reconnect is painless.
		for (int32 i = FirstGamepad; i < MaxPads; ++i)
		{
			FFuryPad& P = Pads[i];
			if (P.Kind == EFuryPadKind::Gamepad && !P.bSeen && P.bConnected)
			{
				P.bConnected = false;
				P.RawStick = FVector2D::ZeroVector;
				FMemory::Memzero(P.Raw);
				UE_LOG(LogFury, Log, TEXT("Input: pad slot %d disconnected"), i);
			}
		}
	}
}

#endif // PLATFORM_MAC
