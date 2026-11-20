#include "FuryInput.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "FuryOptions.h"
#include "Engine/Texture2D.h"
#include "InputKeyEventArgs.h"
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryKeyboardTest, "Fury.Input.KeyboardEdges",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FFuryKeyboardTest::RunTest(const FString&)
{
	FFuryInput& Input = FFuryInput::Get();
	const FFuryPad& Pad = Input.Pad(FFuryInput::KeyboardA);
	auto Key = [&](FKey KeyName, EInputEvent Event)
	{
		FInputKeyEventArgs Args;
		Args.Key = KeyName;
		Args.Event = Event;
		Input.HandleKey(Args);
	};
	auto Tick = [&]() { Input.Tick(1.f / 120.f); };
	Input.ReleaseKeyboard();
	Tick();
	Key(EKeys::G, IE_Pressed);
	Key(EKeys::G, IE_Released);
	Tick();
	TestTrue(TEXT("A complete tap between ticks is delivered once"), Pad.WasPressed(EFuryButton::A) && Pad.WasReleased(EFuryButton::A) && !Pad.IsDown(EFuryButton::A));
	Tick();
	TestFalse(TEXT("No duplicate press on the following tick"), Pad.WasPressed(EFuryButton::A));
	Key(EKeys::G, IE_Pressed);
	Key(EKeys::SpaceBar, IE_Pressed);
	Key(EKeys::G, IE_Released);
	Tick();
	TestTrue(TEXT("Holding the other confirm key keeps the action held"), Pad.IsDown(EFuryButton::A) && !Pad.WasReleased(EFuryButton::A));
	Key(EKeys::D, IE_Pressed);
	Key(EKeys::D, IE_Released);
	Tick();
	TestEqual(TEXT("A short right tap moves exactly one menu cell"), Pad.NavX, 1);
	Key(EKeys::A, IE_Pressed);
	Tick();
	Key(EKeys::D, IE_Pressed);
	Tick();
	TestEqual(TEXT("Opposing keys cancel navigation"), Pad.NavX, 0);
	Input.ReleaseKeyboard();
	Tick();
	TestTrue(TEXT("Losing focus releases movement and both confirm aliases"), Pad.Stick.IsNearlyZero() && !Pad.IsDown(EFuryButton::A));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryReconnectTest, "Fury.Input.ReconnectSeats",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryReconnectTest::RunTest(const FString&)
{
	FFuryInput Input;
	const int32 First = Input.PadForNative(11, TEXT("Xbox"));
	const int32 Second = Input.PadForNative(12, TEXT("DualSense"));
	Input.Pad(First).bConnected = false;
	Input.Pad(Second).bConnected = false;
	TestEqual(TEXT("Second model returns first with a new object"), Input.PadForNative(26, TEXT("DualSense")), Second);
	TestEqual(TEXT("First model returns to its own seat"), Input.PadForNative(27, TEXT("Xbox")), First);
	TestEqual(TEXT("Polling again keeps the same slot"), Input.PadForNative(26, TEXT("DualSense")), Second);
	Input.Pad(First).bConnected = false;
	TestEqual(TEXT("A replacement controller can take a vacant seat"), Input.PadForNative(31, TEXT("Switch Pro")), First);
	return true;
}

#if PLATFORM_MAC
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryNativeGlyphTest, "Fury.Input.MappedControllerGlyphs",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryNativeGlyphTest::RunTest(const FString&)
{
	TestNull(TEXT("Missing platform markings use the standard button prompt"), FFuryInput::MakeFaceTexture(NAME_None));
	for (const TCHAR* Symbol : {TEXT("a.circle"), TEXT("xmark.circle"), TEXT("triangle.fill")})
	{
		UTexture2D* Icon = FFuryInput::MakeFaceTexture(FName(Symbol));
		if (!TestNotNull(Symbol, Icon)) { continue; }
		FTexture2DMipMap& Mip = Icon->GetPlatformData()->Mips[0];
		const uint8* Pixels = static_cast<const uint8*>(Mip.BulkData.LockReadOnly());
		int32 Upper = 0, Lower = 0;
		for (int32 y = 0; y < Mip.SizeY; ++y)
		{
			for (int32 x = 0; x < Mip.SizeX; ++x)
			{
				if (Pixels[(y * Mip.SizeX + x) * 4 + 3] > 128) { (y < Mip.SizeY / 2 ? Upper : Lower)++; }
			}
		}
		Mip.BulkData.Unlock();
		TestTrue(TEXT("System button has a visible mark and transparent margins"), Upper + Lower > 100 && Upper + Lower < Mip.SizeX * Mip.SizeY - 100);
		if (FCString::Strcmp(Symbol, TEXT("triangle.fill")) == 0) { TestTrue(TEXT("The triangle points up on the canvas"), Lower > Upper); }
	}
	return true;
}
#endif

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryCaptionOptionTest, "Fury.Audio.CaptionOptions",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryCaptionOptionTest::RunTest(const FString&)
{
	FFuryOptions Options;
	Options.ToggleMute(EFuryOption::Announcer);
	Options.Adjust(EFuryOption::Captions, 1);
	TestEqual(TEXT("Captions remain available with commentary muted"), Options.Get(EFuryOption::Captions), 1);
	Options.ToggleMute(EFuryOption::Captions);
	TestFalse(TEXT("The caption toggle is independent of mute controls"), Options.Muted(EFuryOption::Captions));
	TestTrue(TEXT("The commentary mute persists"), Options.Muted(EFuryOption::Announcer));
	Options.Reset(false);
	TestEqual(TEXT("Graphics reset preserves captions"), Options.Get(EFuryOption::Captions), 1);
	Options.Reset(true);
	TestEqual(TEXT("Sound reset restores caption default"), Options.Get(EFuryOption::Captions), 0);
	TestEqual(TEXT("Sound reset restores commentary"), Options.Volume(EFuryOption::Announcer), 1.f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FFuryScaleTest, "Fury.Graphics.AdaptiveRenderScale",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)
bool FFuryScaleTest::RunTest(const FString&)
{
	FFuryAutoScale Controller;
	float Scale = 100.f;
	auto Feed = [&](int32 Frames, float Cost, float Budget, float Limit)
	{
		for (int32 i = 0; i < Frames; ++i) { Scale = Controller.Sample(1.f / 120.f, Cost, Budget, Scale, Limit); }
	};
	Feed(70, 18.f, 8.33f, 100.f);
	TestEqual(TEXT("A transient spike cannot drop resolution"), Scale, 100.f);
	Feed(20, 18.f, 8.33f, 100.f);
	TestEqual(TEXT("Sustained GPU cost reduces scale one step"), Scale, 90.f);
	Feed(1000, 18.f, 8.33f, 100.f);
	TestEqual(TEXT("GPU pressure respects the field resolution floor"), Scale, 62.f);
	Feed(90, 3.f, 8.33f, 100.f);
	TestEqual(TEXT("A brief gap cannot raise resolution"), Scale, 62.f);
	Feed(5000, 3.f, 8.33f, 100.f);
	TestEqual(TEXT("Sustained headroom restores the configured ceiling"), Scale, 100.f);
	Controller.Reset();
	Feed(1000, 12.f, 16.67f, 100.f);
	TestEqual(TEXT("A 60 FPS cap uses its longer GPU budget"), Scale, 100.f);
	TestEqual(TEXT("Missing GPU time leaves scale alone"), Controller.Sample(0.01f, 0.f, 8.33f, Scale, 100.f), 100.f);
	TestEqual(TEXT("Suspension gaps do not affect the next game"), Controller.Sample(2.f, 45.f, 8.33f, Scale, 100.f), 100.f);
	return true;
}
#endif
