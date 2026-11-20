#pragma once

#include "CoreMinimal.h"

enum class EFuryOption : uint8
{
	Preset, RenderScale, Lighting, Antialiasing, Textures, Crowd, Effects,
	FrameLimit, VSync, ShowFPS, ReducedMotion, Master, Music, Announcer, Field, Ambience, Interface, Captions, Count
};

/** Adjusts the field render scale from measured GPU time. The HUD stays native. */
struct FFuryAutoScale
{
	float Sample(float Dt, float GpuMs, float BudgetMs, float Current, float Ceiling);
	void Reset() { *this = FFuryAutoScale(); }
private:
	float Window = 0.f, TotalMs = 0.f, Headroom = 0.f;
	int32 Count = 0;
};

struct FFuryOptions
{
	using Option = EFuryOption;
	static constexpr int32 Count = static_cast<int32>(Option::Count);
	static constexpr int32 GraphicsRows = static_cast<int32>(Option::Master);
	static constexpr int32 SoundRows = Count - GraphicsRows;
	static constexpr int32 ChannelCount = static_cast<int32>(Option::Captions) - GraphicsRows;
	static bool IsChannel(Option Id) { return Id >= Option::Master && Id <= Option::Interface; }

	FFuryOptions();
	int32 Get(Option Id) const { return Values[static_cast<int32>(Id)]; }
	static const TCHAR* Label(Option Id);
	static const TCHAR* Hint(Option Id);
	FString Display(Option Id) const;
	bool Adjust(Option Id, int32 Step);
	bool Muted(Option Channel) const;
	void ToggleMute(Option Channel);
	float Volume(Option Channel) const;
	void Reset(bool bSound);
	void Load();
	void Save() const;
	float ScreenPercent(int32 Height) const;
	float Detail(float EffectivePercent) const;
	int32 FrameCap() const;

private:
	int32 Values[Count] = {};
	int32 MutedChannels = 0;
	void SetPreset(int32 Index);
	int32 MatchingPreset() const;
};
