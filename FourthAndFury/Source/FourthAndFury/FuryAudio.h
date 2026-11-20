#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FuryOptions.h"
#include "FuryAudio.generated.h"

class UAudioComponent;
class USoundBase;
class USoundClass;
class USoundMix;

/**
 * Everything you hear: one-shot effects, the crowd (two beds cross-faded by how exciting things
 * are), looping music, and the stadium announcer, who only says one thing at a time.
 *
 * Sounds are looked up by file name under /Game/Fury/Audio, so the game runs (silently) before
 * the audio has been generated and picks new files up without code changes.
 */
UCLASS()
class UFuryAudio : public UObject
{
	GENERATED_BODY()

public:
	void Init(UObject* InContext, const FFuryOptions& Options);
	void UpdateMix(const FFuryOptions& Options, float FadeTime = 0.04f);
	void Preview(EFuryOption Channel);
	void StopPreview();
	void Shutdown();
	void Tick(float DeltaTime, float Excitement);

	void Play(const TCHAR* Name, float Volume = 1.f, float Pitch = 1.f);
	/** Picks one of Name_1 .. Name_Count at random, with a little pitch variation. */
	void PlayOneOf(const TCHAR* Name, int32 Count, float Volume = 1.f, float PitchSpread = 0.06f);
	/** Announcer line. A line already playing is not interrupted unless bUrgent. */
	void Say(const TCHAR* Name, bool bUrgent = false);
	void SayOneOf(const TCHAR* Name, int32 Count, bool bUrgent = false);
	/** Switches the looping music (empty name = silence), cross-fading. */
	void Music(const TCHAR* Name, float Volume = 0.6f);
	/** A looping sound that fades in and out as it is switched on and off. */
	void SetLoop(const TCHAR* Name, bool bOn, float Volume = 0.6f, float Pitch = 1.f);
	void FadeFieldLoops();
	void SetCrowd(bool bOn) { bCrowd = bOn; }
	const FString& Caption() const { return ActiveCaption; }
	bool HasSounds() const { return bAnySound; }

private:
	UAudioComponent* StartClip(USoundBase* Sound, float Volume, float Pitch, bool bAutoDestroy);
	UPROPERTY()
	TObjectPtr<USoundMix> Mixer;
	UPROPERTY()
	TArray<TObjectPtr<USoundClass>> Channels;
	UPROPERTY()
	TObjectPtr<UAudioComponent> PreviewClip;

	USoundBase* Find(const FString& Name);
	UAudioComponent* Loop(const FString& Name, float Volume);

	UPROPERTY()
	TMap<FName, TObjectPtr<USoundBase>> Sounds;

	UPROPERTY()
	TMap<FName, TObjectPtr<UAudioComponent>> Loops;

	UPROPERTY()
	TObjectPtr<UAudioComponent> Voice;

	UPROPERTY()
	TObjectPtr<UAudioComponent> MusicNow;

	UPROPERTY()
	TObjectPtr<UAudioComponent> MusicOld;

	UPROPERTY()
	TObjectPtr<UObject> Context;

	TMap<FName, float> LoopTarget, LoopNow;
	FName MusicName;
	float MusicVolume = 0.6f, PreviousMusicGain = 0.f, MusicFade = 1.f;
	float AnnouncerGain = 1.f, BedGain = 1.f;
	bool bMusicPreview = false;
	float MusicBedGain = 1.f;
	float CrowdLevel = 0.2f;
	float VoiceCooldown = 0.f;
	TMap<FName, FString> VoiceText;
	FString ActiveCaption;
	float CaptionTime = 0.f;
	bool bCrowd = true;
	bool bAnySound = false;
	FRandomStream Random;
};
