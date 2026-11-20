#include "FuryAudio.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "AudioDeviceManager.h"
#include "Engine/Engine.h"
#include "Sound/SoundClass.h"
#include "Sound/SoundMix.h"
#include "Components/AudioComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundBase.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	constexpr int32 FirstChannel = static_cast<int32>(EFuryOption::Music);
	EFuryOption ChannelFor(const FString& Name)
	{
		if (Name.StartsWith(TEXT("MUS_"))) { return EFuryOption::Music; }
		if (Name.StartsWith(TEXT("VO_"))) { return EFuryOption::Announcer; }
		if (Name.StartsWith(TEXT("AMB_"))) { return EFuryOption::Ambience; }
		if (Name.StartsWith(TEXT("SFX_UI"))) { return EFuryOption::Interface; }
		return EFuryOption::Field;
	}
}

void UFuryAudio::Init(UObject* InContext, const FFuryOptions& Options)
{
	Context = InContext;
	Random.Initialize(977);
	Mixer = NewObject<USoundMix>(this);
	Mixer->FadeInTime = 0.f;
	for (int32 i = FirstChannel; i <= static_cast<int32>(EFuryOption::Interface); ++i)
	{
		USoundClass* Channel = NewObject<USoundClass>(this);
		Channels.Add(Channel);
		if (GEngine && GEngine->GetAudioDeviceManager()) { GEngine->GetAudioDeviceManager()->RegisterSoundClass(Channel); }
	}
	UpdateMix(Options, 0.f);
	UGameplayStatics::PushSoundMixModifier(Context, Mixer);
	// First-use synchronous loads during tackles and catches break the cadence of live play.
	const auto& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
	TArray<FAssetData> Clips;
	Registry.GetAssetsByPath(TEXT("/Game/Fury/Audio"), Clips);
	for (const FAssetData& Clip : Clips)
	{
		if (USoundBase* Sound = Cast<USoundBase>(Clip.GetAsset())) { Sounds.Add(Clip.AssetName, Sound); }
	}
	FString Manifest;
	TSharedPtr<FJsonObject> Catalog;
	const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
	if (FFileHelper::LoadFileToString(Manifest, *(FPaths::ProjectContentDir() / TEXT("Data/audio_manifest.json")))
		&& FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Manifest), Catalog) && Catalog.IsValid()
		&& Catalog->TryGetArrayField(TEXT("files"), Entries))
	{
		for (const TSharedPtr<FJsonValue>& Entry : *Entries)
		{
			const TSharedPtr<FJsonObject> Clip = Entry->AsObject();
			FString Key, Line;
			if (Clip && Clip->TryGetStringField(TEXT("name"), Key) && Key.StartsWith(TEXT("VO_"))
				&& Clip->TryGetStringField(TEXT("text"), Line))
			{
				VoiceText.Add(FName(*Key), MoveTemp(Line));
			}
		}
	}
	bAnySound = Find(TEXT("AMB_CrowdLow")) != nullptr || Find(TEXT("SFX_Whistle")) != nullptr;
}

void UFuryAudio::UpdateMix(const FFuryOptions& Options, float FadeTime)
{
	const float Master = Options.Volume(EFuryOption::Master);
	AnnouncerGain = Master * Options.Volume(EFuryOption::Announcer);
	for (int32 i = 0; i < Channels.Num(); ++i)
	{
		const float Gain = Master * Options.Volume(static_cast<EFuryOption>(FirstChannel + i));
		UGameplayStatics::SetSoundMixClassOverride(Context, Mixer, Channels[i], Gain, 1.f, FadeTime, false);
	}
}

UAudioComponent* UFuryAudio::StartClip(USoundBase* Sound, float Volume, float Pitch, bool bAutoDestroy)
{
	if (!Sound) { return nullptr; }
	UAudioComponent* Component = UGameplayStatics::CreateSound2D(Context, Sound, Volume, Pitch, 0.f, nullptr, false, bAutoDestroy);
	if (Component)
	{
		Component->SoundClassOverride = Channels[static_cast<int32>(ChannelFor(Sound->GetName())) - FirstChannel];
		Component->Play();
	}
	return Component;
}

void UFuryAudio::StopPreview()
{
	if (IsValid(PreviewClip)) { PreviewClip->Stop(); }
	PreviewClip = nullptr;
	bMusicPreview = false;
}

void UFuryAudio::Preview(EFuryOption Channel)
{
	StopPreview();
	const TCHAR* Sample = TEXT("SFX_Whistle");
	switch (Channel)
	{
	case EFuryOption::Music:
		Sample = TEXT("MUS_Victory"); break;
	case EFuryOption::Announcer: Sample = TEXT("VO_FirstDown_1"); break;
	case EFuryOption::Ambience: Sample = TEXT("AMB_Cheer_1"); break;
	case EFuryOption::Interface: Sample = TEXT("SFX_UIReady"); break;
	case EFuryOption::Field: Sample = TEXT("SFX_BigHit_1"); break;
	default: break;
	}
	bMusicPreview = Channel == EFuryOption::Music;
	PreviewClip = StartClip(Find(Sample), Channel == EFuryOption::Music ? 0.6f : 1.f, 1.f, true);
	if (PreviewClip && Channel == EFuryOption::Music) { PreviewClip->FadeOut(3.f, 0.f); }
}

void UFuryAudio::Shutdown()
{
	StopPreview();
	if (Mixer) { UGameplayStatics::PopSoundMixModifier(Context, Mixer); }
}

USoundBase* UFuryAudio::Find(const FString& Name)
{
	const FName Key(*Name);
	if (const TObjectPtr<USoundBase>* Found = Sounds.Find(Key))
	{
		return Found->Get();
	}
	USoundBase* Sound = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Fury/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
	Sounds.Add(Key, Sound);      // remember misses too, so a missing file is only looked for once
	return Sound;
}

void UFuryAudio::Play(const TCHAR* Name, float Volume, float Pitch)
{
	if (USoundBase* Sound = Find(Name))
	{
		StartClip(Sound, Volume, Pitch, true);
	}
}

void UFuryAudio::PlayOneOf(const TCHAR* Name, int32 Count, float Volume, float PitchSpread)
{
	const FString Pick = FString::Printf(TEXT("%s_%d"), Name, Random.RandRange(1, FMath::Max(Count, 1)));
	if (USoundBase* Sound = Find(Pick))
	{
		StartClip(Sound, Volume, 1.f + Random.FRandRange(-PitchSpread, PitchSpread), true);
	}
}

void UFuryAudio::Say(const TCHAR* Name, bool bUrgent)
{
	USoundBase* Sound = Find(Name);
	if (!Sound)
	{
		return;
	}
	const bool bBusy = (IsValid(Voice) && Voice->IsPlaying()) || VoiceCooldown > 0.f;
	if (bBusy && !bUrgent)
	{
		return;
	}
	if (IsValid(Voice))
	{
		Voice->Stop();
	}
	Voice = StartClip(Sound, 1.f, 1.f, true);
	// Keep the spoken line and its caption in sync even with a muted or unavailable audio device.
	ActiveCaption = VoiceText.FindRef(FName(Name));
	VoiceCooldown = FMath::Max(0.6f, Sound->GetDuration());
	CaptionTime = FMath::Max(1.45f, VoiceCooldown + 0.18f);
}

void UFuryAudio::SayOneOf(const TCHAR* Name, int32 Count, bool bUrgent)
{
	Say(*FString::Printf(TEXT("%s_%d"), Name, Random.RandRange(1, FMath::Max(Count, 1))), bUrgent);
}

UAudioComponent* UFuryAudio::Loop(const FString& Name, float Volume)
{
	const FName Key(*Name);
	if (const TObjectPtr<UAudioComponent>* Found = Loops.Find(Key))
	{
		if (Found->Get())
		{
			return Found->Get();
		}
	}
	USoundBase* Sound = Find(Name);
	if (!Sound)
	{
		return nullptr;
	}
	UAudioComponent* Component = StartClip(Sound, FMath::Max(Volume, 0.001f), 1.f, false);
	Loops.Add(Key, Component);
	return Component;
}

void UFuryAudio::SetLoop(const TCHAR* Name, bool bOn, float Volume, float Pitch)
{
	const FName Key(Name);
	if (!bOn && !Loops.Contains(Key))
	{
		return;      // never started: nothing to fade out
	}
	if (UAudioComponent* Component = Loop(Name, 0.001f))
	{
		LoopTarget.Add(Key, bOn ? Volume : 0.f);
		if (!LoopNow.Contains(Key)) { LoopNow.Add(Key, 0.f); }
		if (bOn && !FMath::IsNearlyEqual(Component->PitchMultiplier, Pitch, 0.01f)) { Component->SetPitchMultiplier(Pitch); }
		if (bOn && !Component->IsPlaying())
		{
			Component->Play();
		}
	}
}

void UFuryAudio::FadeFieldLoops()
{
	SetLoop(TEXT("SFX_FuryLoop"), false);
	SetLoop(TEXT("SFX_BallAir"), false);
	SetLoop(TEXT("AMB_Chant"), false);
}

void UFuryAudio::Music(const TCHAR* Name, float Volume)
{
	const FName Wanted(Name);
	if (Wanted == MusicName)
	{
		MusicVolume = Volume;
		return;
	}
	PreviousMusicGain = MusicVolume * MusicFade;
	MusicVolume = Volume;
	MusicName = Wanted;
	if (IsValid(MusicOld))
	{
		MusicOld->Stop();
	}
	MusicOld = MusicNow;
	MusicNow = nullptr;
	MusicFade = 0.f;
	if (USoundBase* Sound = Wanted.IsNone() ? nullptr : Find(Name))
	{
		MusicNow = StartClip(Sound, 0.001f, 1.f, true);
	}
}

void UFuryAudio::Tick(float DeltaTime, float Excitement)
{
	VoiceCooldown = FMath::Max(0.f, VoiceCooldown - DeltaTime);
	if (CaptionTime > 0.f)
	{
		CaptionTime -= DeltaTime;
		if (CaptionTime <= 0.f) { ActiveCaption.Reset(); }
	}

	// Make room for the music sample without losing the position of the current track.
	const bool bPreviewing = bMusicPreview && IsValid(PreviewClip) && PreviewClip->IsPlaying();
	MusicBedGain = FMath::FInterpConstantTo(MusicBedGain, bPreviewing ? 0.f : 1.f, DeltaTime, 8.f);
	// Leave space for the call, then bring the stands back up after the line.
	const bool bSpeaking = IsValid(Voice) && Voice->IsPlaying();
	const float BedTarget = bSpeaking ? 1.f - 0.35f * AnnouncerGain : 1.f;
	BedGain = FMath::FInterpConstantTo(BedGain, BedTarget, DeltaTime, bSpeaking ? 4.f : 1.3f);
	// Music cross-fade.
	MusicFade = FMath::Min(1.f, MusicFade + DeltaTime / 0.8f);
	if (IsValid(MusicNow))
	{
		MusicNow->SetVolumeMultiplier(FMath::Max(0.001f, MusicVolume * MusicFade * MusicBedGain * BedGain));
	}
	if (IsValid(MusicOld))
	{
		const float Left = 1.f - MusicFade;
		if (Left <= 0.f)
		{
			MusicOld->Stop();
			MusicOld = nullptr;
		}
		else
		{
			MusicOld->SetVolumeMultiplier(FMath::Max(0.001f, PreviousMusicGain * Left * MusicBedGain * BedGain));
		}
	}

	// Switched loops glide to their volume instead of snapping.
	for (TPair<FName, float>& Now : LoopNow)
	{
		const float Target = LoopTarget.FindRef(Now.Key);
		Now.Value = FMath::FInterpConstantTo(Now.Value, Target, DeltaTime, Target > Now.Value ? 4.f : 2.5f);
		if (const TObjectPtr<UAudioComponent>* Component = Loops.Find(Now.Key))
		{
			if (UAudioComponent* LoopClip = Component->Get())
			{
				const float Gain = FMath::Max(0.001f, Now.Value);
				if (LoopClip->VolumeMultiplier != Gain) { LoopClip->SetVolumeMultiplier(Gain); }
				if (Now.Value == 0.f && Target == 0.f && LoopClip->IsPlaying()) { LoopClip->Stop(); }
			}
		}
	}

	// The crowd: a murmur that is always there, and a roar that swells with the action. The two
	// beds are different people, so they are mixed with an equal-power cross-fade.
	CrowdLevel = FMath::Lerp(CrowdLevel, bCrowd ? Excitement : 0.f, FMath::Min(1.f, DeltaTime * 2.5f));
	const float Presence = bCrowd ? BedGain : 0.f;
	const float Angle = FMath::Clamp(CrowdLevel, 0.f, 1.f) * UE_HALF_PI;
	if (UAudioComponent* Low = Loop(TEXT("AMB_CrowdLow"), 0.4f))
	{
		Low->SetVolumeMultiplier(FMath::Max(0.001f, Presence * (0.35f + 0.65f * FMath::Cos(Angle))));
	}
	if (UAudioComponent* High = Loop(TEXT("AMB_CrowdHigh"), 0.001f))
	{
		High->SetVolumeMultiplier(FMath::Max(0.001f, Presence * FMath::Sin(Angle) * 0.9f));
	}
	if (UAudioComponent* Night = Loop(TEXT("AMB_Night"), 0.2f))
	{
		Night->SetVolumeMultiplier(0.25f);
	}
}
