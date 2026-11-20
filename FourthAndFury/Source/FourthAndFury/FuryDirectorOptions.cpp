#include "FuryDirector.h"
#include "FuryAudio.h"
#include "FuryInput.h"
#include "FuryStadium.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"

namespace
{
	template<typename T>
	void SetRenderOption(const TCHAR* Name, T Value)
	{
		if (IConsoleVariable* CVar = IConsoleManager::Get().FindConsoleVariable(Name))
		{
			if (CVar->GetFloat() != static_cast<float>(Value)) { CVar->Set(Value, ECVF_SetByCode); }
		}
	}
}

void AFuryDirector::ApplyGraphics()
{
	using Opt = EFuryOption;
	const int32 AA = Options.Get(Opt::Antialiasing);
	SetRenderOption(TEXT("r.AntiAliasingMethod"), FMath::Min(AA, 2));
	SetRenderOption(TEXT("r.TemporalAA.Quality"), AA == 3 ? 2 : 1);
	const int32 Texture = Options.Get(Opt::Textures);
	const int32 Anisotropy[] = {1, 4, 8, 16};
	const float MipBias[] = {1.f, 0.5f, 0.f, -0.5f};
	SetRenderOption(TEXT("r.MaxAnisotropy"), Anisotropy[Texture]);
	SetRenderOption(TEXT("r.MipMapLODBias"), MipBias[Texture]);
	SetRenderOption(TEXT("foliage.DensityScale"), 0.25f * (Options.Get(Opt::Crowd) + 1));
	if (Stadium) { Stadium->SetLightingQuality(Options.Get(Opt::Lighting)); }
	const float Density[] = {0.35f, 0.65f, 1.f, 1.5f};
	Effects.ParticleDensity = Density[Options.Get(Opt::Effects)];
	SetRenderOption(TEXT("t.MaxFPS"), static_cast<float>(Options.FrameCap()));
	SetRenderOption(TEXT("r.VSync"), Options.Get(Opt::VSync));
	SizedFor = 0;
}

void AFuryDirector::OpenSettings(int32 Pad)
{
	SettingsPad = Pad;
	bSoundTab = false;
	SettingsRow = 0;
	IdleTime = 0.f;
}

void AFuryDirector::TickSettings()
{
	const FFuryPad& Pad = FFuryInput::Get().Pad(SettingsPad);
	if (!Pad.bConnected || Pad.WasPressed(EFuryButton::B) || Pad.WasPressed(EFuryButton::Start) || Pad.WasPressed(EFuryButton::Back))
	{
		Audio->StopPreview();
		SettingsPad = INDEX_NONE;
		Audio->Play(TEXT("SFX_UIBack"));
		return;
	}
	if (Pad.WasPressed(EFuryButton::LB) || Pad.WasPressed(EFuryButton::RB))
	{
		bSoundTab = !bSoundTab;
		SettingsRow = 0;
		Audio->StopPreview();
		Audio->Play(TEXT("SFX_UIPage"));
		return;
	}
	const int32 RowCount = bSoundTab ? FFuryOptions::SoundRows : FFuryOptions::GraphicsRows;
	const int32 NewRow = FMath::Clamp(SettingsRow - Pad.NavY, 0, RowCount - 1);
	if (SettingsRow != NewRow) { Audio->Play(TEXT("SFX_UIMove")); }
	SettingsRow = NewRow;
	const EFuryOption Selected = static_cast<EFuryOption>((bSoundTab ? FFuryOptions::GraphicsRows : 0) + SettingsRow);
	if (Pad.WasPressed(EFuryButton::X))
	{
		Options.Reset(bSoundTab);
	}
	else if (FFuryOptions::IsChannel(Selected) && Pad.WasPressed(EFuryButton::Y))
	{
		Options.ToggleMute(Selected);
	}
	else if (!Pad.NavX || !Options.Adjust(Selected, Pad.NavX))
	{
		if (FFuryOptions::IsChannel(Selected) && Pad.WasPressed(EFuryButton::A)) { Audio->Preview(Selected); }
		return;
	}
	if (bSoundTab) { Audio->UpdateMix(Options); }
	else { ApplyGraphics(); }
	Options.Save();
	Audio->Play(TEXT("SFX_UIMove"));
}

void AFuryDirector::UpdateFrameMeter()
{
	const double Now = FPlatformTime::Seconds();
	if (MeterLast == 0.0 || Now - MeterLast > 1.0)
	{
		MeterStart = Now;
		MeterFrames = 0;
		LiveFPS = 0.f;
	}
	else
	{
		++MeterFrames;
		const double Elapsed = Now - MeterStart;
		if (Elapsed >= 0.5)
		{
			LiveFPS = static_cast<float>(MeterFrames / Elapsed);
			MeterStart = Now;
			MeterFrames = 0;
		}
	}
	MeterLast = Now;
}

void AFuryDirector::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	FinishAudioCapture();
	if (PriorCaptureDelta > 0.0) { FApp::SetFixedDeltaTime(PriorCaptureDelta); }
	if (PriorAudioTick != INDEX_NONE)
	{
		if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("au.nrt.RenderEveryTick"))) { Var->Set(PriorAudioTick, ECVF_SetByCode); }
	}
	if (Audio) { Audio->Shutdown(); }
	Super::EndPlay(EndPlayReason);
}
