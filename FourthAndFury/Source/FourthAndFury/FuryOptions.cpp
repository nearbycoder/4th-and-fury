#include "FuryOptions.h"
#include "Misc/ConfigCacheIni.h"

namespace
{
	using Opt = EFuryOption;
	struct FOptionInfo { const TCHAR* Key; const TCHAR* Label; const TCHAR* Hint; int32 Max; };
	constexpr FOptionInfo Info[] = {
		{TEXT("Preset"), TEXT("Quality preset"), TEXT("Change the field, lighting and stadium detail together."), 3},
		{TEXT("RenderScale"), TEXT("Render scale"), TEXT("Auto aims for 120 FPS or your lower cap. Fixed scales hold detail."), 6},
		{TEXT("Lighting"), TEXT("Stadium lighting"), TEXT("Add floodlight shadows and, on Ultra, illuminated haze."), 3},
		{TEXT("Antialiasing"), TEXT("Anti-aliasing"), TEXT("Smooth helmet edges, bleachers and distant yard lines."), 3},
		{TEXT("Textures"), TEXT("Texture detail"), TEXT("Keep turf and uniform textures sharper at a distance."), 3},
		{TEXT("Crowd"), TEXT("Crowd density"), TEXT("Choose how many spectators fill the stands."), 3},
		{TEXT("Effects"), TEXT("Particle effects"), TEXT("Set the number of sparks, impact particles and fireworks."), 3},
		{TEXT("FrameLimit"), TEXT("Frame-rate limit"), TEXT("Cap the frame rate or let the renderer run freely."), 5},
		{TEXT("VSync"), TEXT("Vertical sync"), TEXT("Synchronize frame presentation with your display."), 1},
		{TEXT("ShowFPS"), TEXT("Match FPS display"), TEXT("Keep the live frame rate and frame time visible during play."), 1},
		{TEXT("ReducedMotion"), TEXT("Reduced motion"), TEXT("Steady menu camera. Disable impact shake and stadium flashes."), 1},
		{TEXT("Master"), TEXT("Master volume"), TEXT("Adjust the entire mix, including menus and previews."), 20},
		{TEXT("Music"), TEXT("Music"), TEXT("Adjust the theme, play selection and victory music."), 20},
		{TEXT("Announcer"), TEXT("Announcer"), TEXT("Adjust commentary and stadium announcements."), 20},
		{TEXT("Field"), TEXT("Field effects"), TEXT("Adjust tackles, whistles, cleats and ball sounds."), 20},
		{TEXT("Ambience"), TEXT("Crowd and stadium"), TEXT("Adjust crowd beds, chants, cheers and night ambience."), 20},
		{TEXT("Interface"), TEXT("Menu sounds"), TEXT("Adjust feedback while navigating and choosing options."), 20},
		{TEXT("Captions"), TEXT("Announcer captions"), TEXT("Show the announcer’s words, even when the sound is muted."), 1}
	};
	static_assert(UE_ARRAY_COUNT(Info) == FFuryOptions::Count);
	const TCHAR* const PresetNames[] = {TEXT("Performance"), TEXT("Balanced"), TEXT("High"), TEXT("Ultra")};
	const TCHAR* const Levels[] = {TEXT("Low"), TEXT("Medium"), TEXT("High"), TEXT("Ultra")};
	const TCHAR* const AntiAliasing[] = {TEXT("Off"), TEXT("FXAA"), TEXT("Temporal"), TEXT("Temporal high")};
	const int32 Percents[] = {0, 60, 75, 85, 100, 125, 150};
	const int32 FrameCaps[] = {30, 60, 90, 120, 144, 0};
	// Render scale, lighting, anti-aliasing, textures, crowd, effects.
	constexpr int32 Presets[][6] = {{2, 0, 1, 1, 0, 0}, {0, 1, 3, 2, 3, 2}, {4, 2, 3, 3, 3, 2}, {6, 3, 3, 3, 3, 3}};
	static_assert(static_cast<int32>(Opt::Effects) - static_cast<int32>(Opt::RenderScale) + 1 == UE_ARRAY_COUNT(Presets[0]));
	const TCHAR* Section = TEXT("FourthAndFury.Options");
}

FFuryOptions::FFuryOptions()
{
	Reset(false);
	Reset(true);
}

void FFuryOptions::SetPreset(int32 Index)
{
	Values[static_cast<int32>(Opt::Preset)] = Index;
	for (int32 i = 0; i < UE_ARRAY_COUNT(Presets[0]); ++i)
	{
		Values[static_cast<int32>(Opt::RenderScale) + i] = Presets[Index][i];
	}
}

int32 FFuryOptions::MatchingPreset() const
{
	for (int32 i = 0; i < UE_ARRAY_COUNT(Presets); ++i)
	{
		if (FMemory::Memcmp(Values + static_cast<int32>(Opt::RenderScale), Presets[i], sizeof(Presets[i])) == 0) { return i; }
	}
	return INDEX_NONE;
}

void FFuryOptions::Reset(bool bSound)
{
	if (bSound)
	{
		MutedChannels = 0;
		for (int32 i = GraphicsRows; i < GraphicsRows + ChannelCount; ++i) { Values[i] = Info[i].Max; }
		Values[static_cast<int32>(Opt::Captions)] = 0;
		return;
	}
	SetPreset(1);
	Values[static_cast<int32>(Opt::FrameLimit)] = 4;
	Values[static_cast<int32>(Opt::VSync)] = 0;
	Values[static_cast<int32>(Opt::ShowFPS)] = 0;
	Values[static_cast<int32>(Opt::ReducedMotion)] = 0;
}

bool FFuryOptions::Adjust(Option Id, int32 Step)
{
	if (Id == Opt::Preset)
	{
		const int32 Current = MatchingPreset();
		const int32 Base = Current == INDEX_NONE ? Get(Opt::Preset) : Current;
		const int32 Next = FMath::Clamp(Base + Step, 0, 3);
		if (Next == Current) { return false; }
		SetPreset(Next);
		return true;
	}
	const int32 Index = static_cast<int32>(Id);
	const int32 Next = FMath::Clamp(Values[Index] + Step, 0, Info[Index].Max);
	if (IsChannel(Id) && Muted(Id)) { ToggleMute(Id); }
	else if (Next == Values[Index]) { return false; }
	Values[Index] = Next;
	return true;
}

bool FFuryOptions::Muted(Option Channel) const
{
	return IsChannel(Channel) && (MutedChannels & (1 << (static_cast<int32>(Channel) - GraphicsRows))) != 0;
}

void FFuryOptions::ToggleMute(Option Channel)
{
	if (IsChannel(Channel)) { MutedChannels ^= 1 << (static_cast<int32>(Channel) - GraphicsRows); }
}

float FFuryOptions::Volume(Option Channel) const
{
	return Muted(Channel) ? 0.f : Get(Channel) / 20.f;
}

const TCHAR* FFuryOptions::Label(Option Id) { return Info[static_cast<int32>(Id)].Label; }
const TCHAR* FFuryOptions::Hint(Option Id) { return Info[static_cast<int32>(Id)].Hint; }

FString FFuryOptions::Display(Option Id) const
{
	const int32 Value = Get(Id);
	switch (Id)
	{
	case Opt::Preset: { const int32 Match = MatchingPreset(); return Match == INDEX_NONE ? TEXT("Custom") : PresetNames[Match]; }
	case Opt::RenderScale: return Value ? FString::Printf(TEXT("%d%%"), Percents[Value]) : TEXT("Auto");
	case Opt::Antialiasing: return AntiAliasing[Value];
	case Opt::FrameLimit: return FrameCap() ? FString::Printf(TEXT("%d FPS"), FrameCap()) : TEXT("Unlimited");
	case Opt::VSync: case Opt::ShowFPS: case Opt::ReducedMotion: case Opt::Captions: return Value ? TEXT("On") : TEXT("Off");
	case Opt::Crowd: return FString::Printf(TEXT("%d%%"), (Value + 1) * 25);
	case Opt::Lighting: case Opt::Textures: case Opt::Effects: return Levels[Value];
	default: return Muted(Id) ? TEXT("Muted") : FString::Printf(TEXT("%d%%"), Value * 5);
	}
}

int32 FFuryOptions::FrameCap() const { return FrameCaps[Get(Opt::FrameLimit)]; }

float FFuryOptions::ScreenPercent(int32 Height) const
{
	const int32 Fixed = Percents[Get(Opt::RenderScale)];
	return Fixed ? Fixed : FMath::Clamp(108000.f / FMath::Max(Height, 1), 50.f, 100.f);
}

float FFuryAutoScale::Sample(float Dt, float GpuMs, float BudgetMs, float Current, float Ceiling)
{
	if (Dt <= 0.f || Dt > 0.15f || GpuMs <= 0.f || GpuMs > 100.f) { return Current; }
	Window += Dt;
	TotalMs += GpuMs;
	++Count;
	if (Window < 0.65f) { return Current; }
	const float Cost = TotalMs / Count;
	Headroom = Cost < BudgetMs * 0.76f ? Headroom + Window : 0.f;
	Window = TotalMs = 0.f;
	Count = 0;
	const float Floor = FMath::Min(Ceiling, FMath::Max(50.f, Ceiling * 0.62f));
	if (Cost > BudgetMs * 1.03f)
	{
		const float Wanted = Current * FMath::Sqrt(BudgetMs * 0.95f / Cost);
		return FMath::Clamp(FMath::RoundToFloat(Wanted), FMath::Max(Floor, Current - 10.f), Current);
	}
	if (Headroom >= 2.4f)
	{
		Headroom = 0.f;
		return FMath::Min(Ceiling, Current + 3.f);
	}
	return Current;
}

float FFuryOptions::Detail(float EffectivePercent) const
{
	float Sum = FMath::Clamp((EffectivePercent - 50.f) / 100.f, 0.f, 1.f) * 3.f;
	for (int32 i = static_cast<int32>(Opt::Lighting); i <= static_cast<int32>(Opt::Effects); ++i) { Sum += Values[i] / 3.f; }
	return Sum / 8.f;
}

void FFuryOptions::Load()
{
	GConfig->GetInt(Section, TEXT("MutedChannels"), MutedChannels, GGameUserSettingsIni);
	MutedChannels &= (1 << ChannelCount) - 1;
	for (int32 i = 0; i < Count; ++i)
	{
		int32 Value;
		if (GConfig->GetInt(Section, Info[i].Key, Value, GGameUserSettingsIni))
		{
			Values[i] = FMath::Clamp(Value, 0, Info[i].Max);
		}
	}
}

void FFuryOptions::Save() const
{
	GConfig->SetInt(Section, TEXT("MutedChannels"), MutedChannels, GGameUserSettingsIni);
	for (int32 i = 0; i < Count; ++i) { GConfig->SetInt(Section, Info[i].Key, Values[i], GGameUserSettingsIni); }
	GConfig->Flush(false, GGameUserSettingsIni);
}
