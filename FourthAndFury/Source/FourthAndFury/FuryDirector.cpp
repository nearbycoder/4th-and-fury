#include "FuryDirector.h"

#include "AudioDeviceManager.h"
#include "AudioMixerBlueprintLibrary.h"
#include "AudioMixerDevice.h"
#include "AudioMixerPlatformNonRealtime.h"
#include "Camera/CameraComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/DirectionalLight.h"
#include "Engine/Engine.h"
#include "DynamicRHI.h"
#include "Engine/GameViewportClient.h"
#include "FuryGame.h"
#include "HAL/IConsoleManager.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/Texture.h"
#include "Engine/World.h"
#include "FuryAthlete.h"
#include "FuryAudio.h"
#include "FuryInput.h"
#include "FuryStadium.h"
#include "FuryTest.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Sound/SampleBufferIO.h"
#include "UnrealClient.h"

namespace
{
	const float QuarterOptions[] = { 60.f, 90.f, 120.f, 180.f };
	const float SkillOptions[] = { 0.25f, 0.5f, 0.8f };
}

AFuryDirector::AFuryDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Root);
	Camera->bConstrainAspectRatio = false;
	Camera->PostProcessBlendWeight = 1.f;
}

FLinearColor AFuryDirector::SeatColor(int32 Seat)
{
	static const FLinearColor Colors[Fury::MaxSeats] = {
		FLinearColor(1.f, 0.16f, 0.14f), FLinearColor(0.12f, 0.5f, 1.f), FLinearColor(1.f, 0.82f, 0.08f), FLinearColor(0.2f, 0.9f, 0.3f),
		FLinearColor(1.f, 0.45f, 0.05f), FLinearColor(0.72f, 0.3f, 1.f), FLinearColor(0.1f, 0.9f, 0.9f), FLinearColor(1.f, 0.4f, 0.75f) };
	return Colors[FMath::Clamp(Seat, 0, Fury::MaxSeats - 1)];
}

const TCHAR* AFuryDirector::SkillName(int32 Choice)
{
	static const TCHAR* Names[] = { TEXT("ROOKIE"), TEXT("PRO"), TEXT("ALL-FURY") };
	return Names[FMath::Clamp(Choice, 0, 2)];
}

float AFuryDirector::QuarterSeconds() const
{
	return QuarterOptions[FMath::Clamp(QuarterChoice, 0, 3)];
}

float AFuryDirector::Skill() const
{
	return SkillOptions[FMath::Clamp(SkillChoice, 0, 2)];
}

const FFuryPad* AFuryDirector::SeatPad(int32 Seat) const
{
	if (Seat < 0 || Seat >= Fury::MaxSeats) { return nullptr; }
	const FFuryLobbySeat& S = Seats[Seat];
	return S.bJoined && S.Pad != INDEX_NONE ? &FFuryInput::Get().Pad(S.Pad) : nullptr;
}

int32 AFuryDirector::NumJoined() const
{
	int32 Count = 0;
	for (const FFuryLobbySeat& S : Seats) { Count += S.bJoined ? 1 : 0; }
	return Count;
}

int32 AFuryDirector::NumOnSide(int32 Side) const
{
	int32 Count = 0;
	for (const FFuryLobbySeat& S : Seats) { Count += (S.bJoined && S.Side == Side) ? 1 : 0; }
	return Count;
}

int32 AFuryDirector::Picker(int32 Side) const
{
	// The first human on a side picks its team; a computer side is picked by the first human at the table.
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		if (Seats[i].bJoined && Seats[i].Side == Side && !Seats[i].bBot) { return i; }
	}
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		if (Seats[i].bJoined && !Seats[i].bBot) { return i; }
	}
	return INDEX_NONE;
}

UTexture* AFuryDirector::UiTexture(const TCHAR* Name) const
{
	if (const TObjectPtr<UTexture>* Found = Textures.Find(Name))
	{
		return Found->Get();
	}
	UTexture* Texture = LoadObject<UTexture>(nullptr, *FString::Printf(TEXT("/Game/Fury/Textures/%s.%s"), Name, Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
	Textures.Add(Name, Texture);
	return Texture;
}

UTexture* AFuryDirector::TeamLogo(int32 League) const
{
	const TArray<FFuryTeam>& All = Fury::Teams();
	return All.IsValidIndex(League) ? UiTexture(*(TEXT("T_Logo_") + All[League].Id)) : nullptr;
}

void AFuryDirector::ShowBanner(const FString& Title, const FString& Detail, const FLinearColor& Color, float Length, bool bBig)
{
	Banner.Title = Title;
	Banner.Detail = Detail;
	Banner.Color = Color;
	Banner.Start = GetWorld()->GetRealTimeSeconds();
	Banner.Length = Length;
	Banner.bBig = bBig;
}

void AFuryDirector::BeginPlay()
{
	Super::BeginPlay();

	int32 TestGames = 0;
	if (FParse::Value(FCommandLine::Get(), TEXT("FurySimTest="), TestGames) && TestGames > 0)
	{
		float TestSkill = 0.5f;
		int32 TestBots = 0;
		FParse::Value(FCommandLine::Get(), TEXT("FurySkill="), TestSkill);
		FParse::Value(FCommandLine::Get(), TEXT("FuryBots="), TestBots);
		Fury::RunSimTest(TestGames, TestSkill, TestBots, FParse::Param(FCommandLine::Get(), TEXT("FuryVerbose")));
		FPlatformMisc::RequestExit(false);
		return;
	}

	bBenchmark = FParse::Param(FCommandLine::Get(), TEXT("FuryBenchmark"));
	bTestPause = FParse::Param(FCommandLine::Get(), TEXT("FuryTestPause"));
	FString Pinned;
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryCam="), Pinned, false))
	{
		TArray<FString> Parts;
		Pinned.ParseIntoArray(Parts, TEXT(","));
		if (Parts.Num() >= 6)
		{
			PinnedEye = FVector(FCString::Atof(*Parts[0]), FCString::Atof(*Parts[1]), FCString::Atof(*Parts[2]));
			PinnedLook = FVector(FCString::Atof(*Parts[3]), FCString::Atof(*Parts[4]), FCString::Atof(*Parts[5]));
			if (Parts.Num() > 6) { PinnedFov = FCString::Atof(*Parts[6]); }
			bPinnedCamera = true;
		}
	}
	FParse::Value(FCommandLine::Get(), TEXT("FurySoakMatches="), SoakMatches);
	FParse::Value(FCommandLine::Get(), TEXT("FuryShots="), ShotDir);
	FParse::Value(FCommandLine::Get(), TEXT("FuryShotEvery="), ShotEvery);
	FParse::Value(FCommandLine::Get(), TEXT("FuryShotFrom="), ShotFrom);
	FParse::Value(FCommandLine::Get(), TEXT("FuryQuitAfter="), QuitAfter);
	FParse::Value(FCommandLine::Get(), TEXT("FuryAudioOut="), AudioOut);
	int32 CaptureFPS = 0;
	if ((!ShotDir.IsEmpty() || !AudioOut.IsEmpty()) && FApp::UseFixedTimeStep()
		&& FParse::Value(FCommandLine::Get(), TEXT("FuryCaptureFPS="), CaptureFPS) && CaptureFPS > 0)
	{
		PriorCaptureDelta = FApp::GetFixedDeltaTime();
		FApp::SetFixedDeltaTime(1.0 / CaptureFPS);
	}
	if (!AudioOut.IsEmpty())
	{
		// The offline mixer otherwise caches its launch-time delta (often 1/30),
		// even when the requested recording runs at 60 frames per second.
		if (const FAudioDevice* Device = GetWorld()->GetAudioDeviceRaw(); Device && Device->IsNonRealtime())
		{
			if (IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("au.nrt.RenderEveryTick")))
			{
				PriorAudioTick = Var->GetInt();
				Var->Set(0, ECVF_SetByCode);
			}
		}
		// Record everything the game plays to a wav, so the mix can be checked without ears.
		UAudioMixerBlueprintLibrary::StartRecordingOutput(this, 0.f);
	}
	FParse::Value(FCommandLine::Get(), TEXT("FuryClip="), ViewerOnly);
	FParse::Value(FCommandLine::Get(), TEXT("FurySpeed="), TimeScale);

	if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
	{
		PC->SetViewTarget(this);
	}

	// Fixed exposure: a night game should not pump brightness as the camera moves.
	FPostProcessSettings& Post = Camera->PostProcessSettings;
	Post.bOverride_AutoExposureMinBrightness = Post.bOverride_AutoExposureMaxBrightness = true;
	Post.AutoExposureMinBrightness = Post.AutoExposureMaxBrightness = 1.f;
	Post.bOverride_AutoExposureBias = true;
	Post.AutoExposureBias = 0.f;
	FParse::Value(FCommandLine::Get(), TEXT("FuryExposure="), Post.AutoExposureBias);
	Post.bOverride_BloomIntensity = true;
	Post.BloomIntensity = 0.55f;
	Post.bOverride_VignetteIntensity = true;
	Post.VignetteIntensity = 0.32f;
	Post.bOverride_MotionBlurAmount = true;
	Post.MotionBlurAmount = 0.f;
	Post.bOverride_MotionBlurMax = true;
	Post.MotionBlurMax = 1.2f;
	Post.bOverride_ColorSaturation = true;
	Post.ColorSaturation = FVector4(1.08, 1.08, 1.08, 1.0);
	Post.bOverride_ColorContrast = true;
	Post.ColorContrast = FVector4(1.06, 1.06, 1.06, 1.0);
	Post.bOverride_FilmSlope = true;
	Post.FilmSlope = 0.9f;

	LoadAssets();
	Audio = NewObject<UFuryAudio>(this);
	Options.Load();
	Audio->Init(this, Options);
	Effects.Init(this);
	ApplyGraphics();
	Sparkle.Initialize(31337);
	if (FParse::Param(FCommandLine::Get(), TEXT("FuryViewer")))
	{
		Screen = EFuryScreen::Viewer;
		BeginViewer();
		return;
	}

	Stadium = GetWorld()->SpawnActor<AFuryStadium>(AFuryStadium::StaticClass(), FTransform::Identity);
	Stadium->Build();
	Stadium->SetLightingQuality(Options.Get(EFuryOption::Lighting));
	// A body for every member of both rosters. Swapping units mid-game then costs nothing: no
	// meshes or materials change, only which athletes are shown.
	for (int32 i = 0; i < 2 * RosterSize; ++i)
	{
		Squad.Add(SpawnAthlete());
		Squad.Last()->SetActorHiddenInGame(true);
	}
	for (int32 i = 0; i < Fury::NumPlayers; ++i)
	{
		Athletes.Add(Squad[(i / Fury::TeamSize) * RosterSize + (i % Fury::TeamSize)]);
	}

	// Test shortcuts.
	FString HomeId, AwayId;
	const TArray<FFuryTeam>& League = Fury::Teams();
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryHome="), HomeId))
	{
		TeamPick[0] = FMath::Max(0, League.IndexOfByPredicate([&HomeId](const FFuryTeam& T) { return T.Id == HomeId; }));
	}
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryAway="), AwayId))
	{
		TeamPick[1] = FMath::Max(0, League.IndexOfByPredicate([&AwayId](const FFuryTeam& T) { return T.Id == AwayId; }));
	}
	float QuarterOverride = 0.f;
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryQuarter="), QuarterOverride))
	{
		QuarterChoice = QuarterOverride <= 60.f ? 0 : QuarterOverride <= 90.f ? 1 : QuarterOverride <= 120.f ? 2 : 3;
	}
	int32 BotCount = 0;
	FParse::Value(FCommandLine::Get(), TEXT("FuryBots="), BotCount);
	for (int32 i = 0; i < FMath::Min(BotCount, Fury::MaxSeats); ++i)
	{
		Seats[i].bJoined = true;
		Seats[i].bBot = true;
		Seats[i].bReady = true;
		Seats[i].Side = i % 2;
		Seats[i].Pad = INDEX_NONE;
	}
	// Interface testing: -FuryFakeSeats=N seats N pretend humans (silent pads) so the lobby and
	// team screens can be looked at without anyone holding a controller.
	int32 FakeCount = 0;
	FParse::Value(FCommandLine::Get(), TEXT("FuryFakeSeats="), FakeCount);
	for (int32 i = 0; i < FMath::Min(FakeCount, Fury::MaxSeats); ++i)
	{
		Seats[i].bJoined = true;
		Seats[i].bBot = false;
		Seats[i].Pad = i == 0 ? FFuryInput::KeyboardA : i == 1 ? FFuryInput::KeyboardB : FFuryInput::Get().AddBot(FString::Printf(TEXT("PAD %d"), i - 1));
		Seats[i].Side = i >= 6 || FParse::Param(FCommandLine::Get(), TEXT("FuryAllWaiting")) ? INDEX_NONE : i % 2;
		Seats[i].bReady = Seats[i].Side != INDEX_NONE && i < 4;
	}
	Stadium->Dress(League[TeamPick[0]], League[TeamPick[1]]);

	FString Jump;
	FParse::Value(FCommandLine::Get(), TEXT("FuryScreen="), Jump);
	if (FParse::Param(FCommandLine::Get(), TEXT("FuryMatch")))
	{
		StartMatch();
	}
	else if (Jump == TEXT("lobby")) { GoTo(EFuryScreen::Lobby); }
	else if (Jump == TEXT("teams")) { GoTo(EFuryScreen::Teams); }
	else { GoTo(EFuryScreen::Title); }
}

void AFuryDirector::LoadAssets()
{
	auto LoadMesh = [](const TCHAR* Path) { return LoadObject<USkeletalMesh>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet); };
	BodyMeshes[0] = LoadMesh(TEXT("/Game/Fury/Characters/SK_Player_Lean.SK_Player_Lean"));
	BodyMeshes[1] = LoadMesh(TEXT("/Game/Fury/Characters/SK_Player_Mid.SK_Player_Mid"));
	BodyMeshes[2] = LoadMesh(TEXT("/Game/Fury/Characters/SK_Player_Big.SK_Player_Big"));
	FString AnimPath = TEXT("/Game/Fury/Anims");
	if (!BodyMeshes[1])
	{
		// Art still in progress: fall back to the pipeline test rig.
		BodyMeshes[1] = LoadMesh(TEXT("/Game/Fury/Test/SK_Blockout.SK_Blockout"));
		AnimPath = TEXT("/Game/Fury/Test");
		UE_LOG(LogFury, Warning, TEXT("Athlete meshes not imported yet; using the blockout rig"));
	}
	AthleteMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Fury/Materials/M_Athlete.M_Athlete"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	AnimSet.Build(BodyMeshes[1], AnimPath, FPaths::ProjectContentDir() / TEXT("Data/anims.json"));
}

AFuryAthlete* AFuryDirector::SpawnAthlete()
{
	AFuryAthlete* Athlete = GetWorld()->SpawnActor<AFuryAthlete>(AFuryAthlete::StaticClass(), FTransform::Identity);
	Athlete->Setup(&AnimSet, BodyMeshes[0], BodyMeshes[1], BodyMeshes[2], AthleteMaterial);
	return Athlete;
}

void AFuryDirector::SetCamera(const FVector& Eye, const FVector& Target, float FieldOfView)
{
	Camera->SetWorldLocationAndRotation(Eye, (Target - Eye).Rotation());
	Camera->SetFieldOfView(FieldOfView);
}

void AFuryDirector::GoTo(EFuryScreen NewScreen)
{
	Screen = NewScreen;
	bViewingFilm = false;
	if (NewScreen != EFuryScreen::Final) { bQuickMatch = false; }
	ScreenTime = 0.f;
	IdleTime = 0.f;
	bPaused = false;
	StartCountdown = -1.f;
	if (NewScreen == EFuryScreen::Title)
	{
		bDemo = false;
		for (FFuryLobbySeat& Seat : Seats)
		{
			if (!Seat.bBot) { Seat = FFuryLobbySeat(); }
		}
	}
	if (NewScreen == EFuryScreen::Lobby && !FParse::Param(FCommandLine::Get(), TEXT("FuryKeepReady")))
	{
		for (FFuryLobbySeat& Seat : Seats) { Seat.bReady = Seat.bBot; }
	}
	if (NewScreen == EFuryScreen::Teams)
	{
		bTeamLocked[0] = bTeamLocked[1] = false;
		OptionRow[0] = OptionRow[1] = 0;
	}
	if (Audio)
	{
		// Menus get the theme; the match gets the crowd.
		const bool bMenu = NewScreen == EFuryScreen::Title || NewScreen == EFuryScreen::Lobby || NewScreen == EFuryScreen::Teams || NewScreen == EFuryScreen::Final;
		Audio->Music(bMenu ? TEXT("MUS_Menu") : TEXT(""), NewScreen == EFuryScreen::Final ? 0.4f : 0.6f);
		Audio->SetCrowd(true);
		Audio->FadeFieldLoops();
		if (NewScreen == EFuryScreen::Title) { Audio->Say(TEXT("VO_Title"), true); }
	}
	Effects.Clear();
	Shadows.Show(NewScreen == EFuryScreen::Match);
	if (Stadium && NewScreen != EFuryScreen::Match) { Stadium->SetChains(0, 0.f, 0.f, 0.f, false); }
	const bool bShowcase = NewScreen == EFuryScreen::Teams;
	if (NewScreen != EFuryScreen::Match)
	{
		for (AFuryAthlete* Athlete : Squad) { Athlete->SetActorHiddenInGame(true); }
		if (BallMesh) { BallMesh->SetVisibility(false); }
		if (TeeMesh) { TeeMesh->SetVisibility(false); }
		if (CatchMarker) { CatchMarker->SetVisibility(false); }
		for (UStaticMeshComponent* Marker : Markers) { Marker->SetVisibility(false); }
		if (ScrimmageLine) { ScrimmageLine->SetVisibility(false); }
		if (FirstDownLine) { FirstDownLine->SetVisibility(false); }
	}
	ShowcaseAthletes(bShowcase);
}

// ---------------------------------------------------------------------------------------------
// Front end
// ---------------------------------------------------------------------------------------------

void AFuryDirector::TickBackdrop(float DeltaTime, float Radius, float Height, float Speed)
{
	// A slow sweep around the bowl behind the menus.
	if (!Options.Get(EFuryOption::ReducedMotion)) { Orbit += DeltaTime * Speed; }
	const FVector Eye(FMath::Cos(Orbit) * Radius, FMath::Sin(Orbit) * Radius * 0.55f + 600.f, Height + FMath::Sin(Orbit * 0.7f) * 250.f);
	SetCamera(Eye, FVector(0.f, -400.f, 500.f), 48.f);
	Excitement = Fury::Approach(Excitement, 0.25f, DeltaTime * 0.3f);
	if (Stadium) { Stadium->SetExcitement(Excitement); }
}

void AFuryDirector::TickQuitPrompt()
{
	const FFuryPad& Pad = FFuryInput::Get().Pad(QuitPad);
	if (!Pad.bConnected || Pad.WasPressed(EFuryButton::B) || Pad.WasPressed(EFuryButton::Back) || Pad.WasPressed(EFuryButton::Start))
	{
		QuitPad = INDEX_NONE;
		IdleTime = 0.f;
		Audio->Play(TEXT("SFX_UIBack"));
	}
	else if (Pad.WasPressed(EFuryButton::A))
	{
		UKismetSystemLibrary::QuitGame(this, nullptr, EQuitPreference::Quit, false);
	}
}

bool AFuryDirector::TryJoinFromTitle()
{
	FFuryInput& Input = FFuryInput::Get();
	for (int32 i = 0; i < FFuryInput::MaxPads; ++i)
	{
		const FFuryPad& Pad = Input.Pad(i);
		if (Pad.Kind == EFuryPadKind::Bot || !Pad.bConnected)
		{
			continue;
		}
		if (FPlatformProperties::SupportsQuit() && Pad.WasPressed(EFuryButton::B))
		{
			if (bDemo) { GoTo(EFuryScreen::Title); }
			QuitPad = i;
			Audio->Play(TEXT("SFX_UISelect"));
			return true;
		}
		if (Pad.WasPressed(EFuryButton::X))
		{
			bDemo = false;
			bQuickMatch = true;
			for (FFuryLobbySeat& Seat : Seats) { Seat = FFuryLobbySeat(); }
			Seats[0].bJoined = Seats[0].bReady = true;
			Seats[0].Side = 0;
			Seats[0].Pad = i;
			Audio->Play(TEXT("SFX_UIJoin"));
			StartMatch();
			return true;
		}
		if (Pad.WasPressed(EFuryButton::Y))
		{
			if (bDemo) { GoTo(EFuryScreen::Title); }
			OpenSettings(i);
			return true;
		}
		if (Pad.WasPressed(EFuryButton::A) || Pad.WasPressed(EFuryButton::Start))
		{
			// Whoever starts the game takes the first seat.
			bDemo = false;
			GoTo(EFuryScreen::Lobby);
			for (FFuryLobbySeat& Seat : Seats)
			{
				if (!Seat.bJoined)
				{
					Seat.bJoined = true;
					Seat.Pad = i;
					break;
				}
			}
			Audio->Play(TEXT("SFX_UIJoin"));
			return true;
		}
	}
	return false;
}

void AFuryDirector::TickTitle(float DeltaTime)
{
	TickBackdrop(DeltaTime, 5200.f, 2300.f, 0.07f);
	if (TryJoinFromTitle()) { return; }
	// Left alone, the game plays itself.
	IdleTime += DeltaTime;
	if (IdleTime > 22.f)
	{
		bDemo = true;
		FRandomStream Random(FDateTime::Now().GetTicks() & 0xffff);
		const int32 Count = Fury::Teams().Num();
		TeamPick[0] = Random.RandRange(0, Count - 1);
		TeamPick[1] = (TeamPick[0] + 1 + Random.RandRange(0, Count - 2)) % Count;
		StartMatch();
	}
}

void AFuryDirector::TickLobby(float DeltaTime)
{
	TickBackdrop(DeltaTime, 4300.f, 1700.f, 0.05f);
	FFuryInput& Input = FFuryInput::Get();

	// Anyone not yet at the table joins with A.
	for (int32 i = 0; i < FFuryInput::MaxPads; ++i)
	{
		const FFuryPad& Pad = Input.Pad(i);
		if (Pad.Kind == EFuryPadKind::Bot || Pad.Kind == EFuryPadKind::None || !Pad.bConnected || !Pad.WasPressed(EFuryButton::A))
		{
			continue;
		}
		bool bSeated = false;
		for (const FFuryLobbySeat& Seat : Seats) { bSeated |= Seat.bJoined && Seat.Pad == i; }
		if (bSeated)
		{
			continue;
		}
		for (FFuryLobbySeat& Seat : Seats)
		{
			if (!Seat.bJoined)
			{
				Seat = FFuryLobbySeat();
				Seat.bJoined = true;
				Seat.Pad = i;
				// Joining swallows this press so it does not also ready the player up.
				Seat.Side = INDEX_NONE;
				StartCountdown = -1.f;
				Audio->Play(TEXT("SFX_UIJoin"));
				break;
			}
		}
	}

	bool bAllReady = NumJoined() > 0;
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		FFuryLobbySeat& Seat = Seats[i];
		if (!Seat.bJoined || Seat.bBot)
		{
			continue;
		}
		const FFuryPad& Pad = Input.Pad(Seat.Pad);
		if (!Pad.bConnected)
		{
			Seat = FFuryLobbySeat();
			StartCountdown = -1.f;
			bAllReady = false;
			continue;
		}
		if (!Seat.bReady && Pad.NavX != 0)
		{
			// Step left toward the home side, right toward the away side.
			const int32 Wanted = FMath::Clamp((Seat.Side == INDEX_NONE ? 0 : Seat.Side == 0 ? -1 : 1) + Pad.NavX, -1, 1);
			const int32 Side = Wanted < 0 ? 0 : Wanted > 0 ? 1 : INDEX_NONE;
			if (Side == INDEX_NONE || Side == Seat.Side || NumOnSide(Side) < Fury::MaxSeatsPerTeam)
			{
				if (Side != Seat.Side) { Audio->Play(TEXT("SFX_UIMove")); }
				Seat.Side = Side;
			}
			else
			{
				Audio->Play(TEXT("SFX_UIError"));
			}
		}
		if (Pad.WasPressed(EFuryButton::A) && Seat.Side != INDEX_NONE && ScreenTime > 0.25f && !Seat.bReady)
		{
			Seat.bReady = true;
			Audio->Play(TEXT("SFX_UIReady"));
		}
		if (Pad.WasPressed(EFuryButton::B))
		{
			Audio->Play(TEXT("SFX_UIBack"));
			if (Seat.bReady) { Seat.bReady = false; }
			else
			{
				Seat = FFuryLobbySeat();
				if (NumJoined() == 0)
				{
					GoTo(EFuryScreen::Title);
					return;
				}
			}
			StartCountdown = -1.f;
		}
		bAllReady &= Seat.bReady && Seat.Side != INDEX_NONE;
	}

	if (bAllReady)
	{
		if (TickCountdown(1.6f, DeltaTime))
		{
			GoTo(EFuryScreen::Teams);
		}
	}
	else
	{
		StartCountdown = -1.f;
	}
}

bool AFuryDirector::TickCountdown(float Length, float DeltaTime)
{
	// Counts down with a tick every beat; true on the frame it runs out.
	const float Beat = 0.6f;
	if (StartCountdown < 0.f)
	{
		StartCountdown = Length;
		Audio->Play(TEXT("SFX_Countdown"));
	}
	const float Before = StartCountdown;
	StartCountdown -= DeltaTime;
	if (StartCountdown > 0.f && FMath::FloorToInt32(Before / Beat) != FMath::FloorToInt32(StartCountdown / Beat))
	{
		Audio->Play(TEXT("SFX_Countdown"));
	}
	return StartCountdown <= 0.f;
}

void AFuryDirector::ShowcaseAthletes(bool bShow)
{
	// Two athletes at midfield wearing the chosen kits, shown on the team-select screen.
	if (Squad.Num() < 2 * RosterSize)
	{
		return;
	}
	for (int32 Side = 0; Side < 2; ++Side)
	{
		AFuryAthlete* Athlete = Squad[Side * RosterSize + Fury::OffenseSlot0];
		Athlete->SetActorHiddenInGame(!bShow);
		if (bShow)
		{
			Athlete->SetLook(MakeLook(Side, Fury::OffenseSlot0));
			DressedLeague[Side] = TeamPick[Side];
		}
	}
}

void AFuryDirector::TickTeams(float DeltaTime)
{
	FFuryInput& Input = FFuryInput::Get();
	const int32 Count = Fury::Teams().Num();
	for (const FFuryLobbySeat& S : Seats)
	{
		if (S.bJoined && !S.bBot && !Input.Pad(S.Pad).bConnected)
		{
			GoTo(EFuryScreen::Lobby);
			return;
		}
	}


	// Camera: close on the two athletes standing at midfield, facing us.
	if (!Options.Get(EFuryOption::ReducedMotion)) { Orbit += DeltaTime * 0.25f; }
	SetCamera(FVector(FMath::Sin(Orbit) * 45.f, 1010.f, 140.f), FVector(0.f, 0.f, 104.f), 30.f);
	for (int32 Side = 0; Side < 2; ++Side)
	{
		if (Squad.Num() < 2 * RosterSize)
		{
			break;
		}
		AFuryAthlete* Athlete = Squad[Side * RosterSize + Fury::OffenseSlot0];
		if (DressedLeague[Side] != TeamPick[Side])
		{
			Athlete->SetLook(MakeLook(Side, Fury::OffenseSlot0));
			DressedLeague[Side] = TeamPick[Side];
		}
		FFuryAthleteState State;
		// Side by side in the gap between the two team cards, turned slightly toward each other.
		State.Pos = FVector2D(Side == 0 ? -50.f : 50.f, 0.f);
		State.Yaw = UE_HALF_PI + (Side == 0 ? -0.3f : 0.3f);
		State.Act = bTeamLocked[Side] ? EFuryAct::Celebrate : EFuryAct::Stand;
		State.Variant = bTeamLocked[Side] ? 2 : static_cast<uint8>(EFuryStance::Idle);
		State.ActTime = ScreenTime;
		State.ActSerial = bTeamLocked[Side] ? 1 : 0;
		Athlete->Advance(State, DeltaTime);
	}

	const bool bSharedPicker = Picker(0) == Picker(1);
	const int32 SharedSide = bTeamLocked[0] ? 1 : 0;
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const int32 Seat = Picker(Side);
		if (Seat == INDEX_NONE)
		{
			bTeamLocked[Side] = true;      // nobody at the table: bots or a demo
			continue;
		}
		// One human choosing for both sides picks the home side first.
		if (bSharedPicker && Side != SharedSide)
		{
			continue;
		}
		const FFuryPad& Pad = Input.Pad(Seats[Seat].Pad);
		if (bTeamLocked[Side])
		{
			if (Pad.WasPressed(EFuryButton::B))
			{
				bTeamLocked[Side] = false;
				Audio->Play(TEXT("SFX_UIBack"));
			}
			continue;
		}
		const int32 Rows = Side == 0 ? 3 : 1;
		const int32 NewRow = FMath::Clamp(OptionRow[Side] - Pad.NavY, 0, Rows - 1);
		if (NewRow != OptionRow[Side] || Pad.NavX != 0) { Audio->Play(TEXT("SFX_UIMove")); }
		OptionRow[Side] = NewRow;
		if (Pad.NavX != 0)
		{
			if (OptionRow[Side] == 0)
			{
				TeamPick[Side] = (TeamPick[Side] + Pad.NavX + Count) % Count;
				if (TeamPick[Side] == TeamPick[1 - Side])
				{
					TeamPick[Side] = (TeamPick[Side] + Pad.NavX + Count) % Count;      // no mirror matches
				}
			}
			else if (OptionRow[Side] == 1) { QuarterChoice = FMath::Clamp(QuarterChoice + Pad.NavX, 0, 3); }
			else { SkillChoice = FMath::Clamp(SkillChoice + Pad.NavX, 0, 2); }
		}
		if (Pad.WasPressed(EFuryButton::A) && ScreenTime > 0.3f)
		{
			bTeamLocked[Side] = true;
			Audio->Play(TEXT("SFX_UISelect"));
			Audio->Say(*(TEXT("VO_Team_") + Fury::Teams()[TeamPick[Side]].Id), true);
		}
		else if (Pad.WasPressed(EFuryButton::B))
		{
			Audio->Play(TEXT("SFX_UIBack"));
			if (bSharedPicker && Side == 1)
			{
				bTeamLocked[0] = false;
				continue;
			}
			GoTo(EFuryScreen::Lobby);
			return;
		}
	}

	if (Stadium && (DressedLeague[0] != INDEX_NONE))
	{
		Stadium->SetExcitement(0.3f);
	}
	if (bTeamLocked[0] && bTeamLocked[1])
	{
		if (TickCountdown(1.8f, DeltaTime))
		{
			Audio->Play(TEXT("SFX_CountdownGo"));
			StartMatch();
		}
	}
	else
	{
		StartCountdown = -1.f;
	}
}

void AFuryDirector::TickFinal(float DeltaTime)
{
	if (SoakMatches > 0 && ScreenTime > 2.f)
	{
		++SoakFinished;
		const uint64 ResidentMiB = FPlatformMemory::GetStats().UsedPhysical / (1024u * 1024u);
		UE_LOG(LogFury, Display, TEXT("FURY_SOAK game=%d/%d score=%d-%d plays=%d film_frames=%d resident_mib=%llu"),
			SoakFinished, SoakMatches, Sim.Teams[0].Score, Sim.Teams[1].Score, Sim.PlayCount, Film.Last.Frames.Num(), ResidentMiB);
		if (SoakFinished < SoakMatches) { StartMatch(); }
		else { FPlatformMisc::RequestExit(false); }
		return;
	}
	if (bViewingFilm)
	{
		const FFuryPad* Pad = SeatPad(PauseSeat);
		if (Pad && Pad->bConnected) { TickFilm(*Pad, DeltaTime); }
		else { bViewingFilm = false; }
		return;
	}
	TickBackdrop(DeltaTime, 4600.f, 2000.f, 0.06f);
	FFuryInput& Input = FFuryInput::Get();
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		const FFuryLobbySeat& Seat = Seats[i];
		if (!Seat.bJoined || Seat.bBot)
		{
			continue;
		}
		const FFuryPad& Pad = Input.Pad(Seat.Pad);
		if (ScreenTime > 1.f && FPlatformProperties::SupportsQuit() && Pad.WasPressed(EFuryButton::X))
		{
			QuitPad = Seat.Pad;
			Audio->Play(TEXT("SFX_UISelect"));
			return;
		}
		if (ScreenTime > 1.f && Pad.WasPressed(EFuryButton::Y) && SelectedFilm().Ready())
		{
			OpenFilm(i);
			return;
		}
		if (ScreenTime > 1.f && Pad.WasPressed(EFuryButton::A))
		{
			StartMatch();      // rematch, same sides and settings
			return;
		}
		if (ScreenTime > 1.f && (Pad.WasPressed(EFuryButton::B) || Pad.WasPressed(EFuryButton::Start)))
		{
			GoTo(EFuryScreen::Teams);
			return;
		}
	}
	if (NumJoined() == 0 && ScreenTime > 12.f)
	{
		GoTo(EFuryScreen::Title);
	}
}

// ---------------------------------------------------------------------------------------------
// Animation viewer
// ---------------------------------------------------------------------------------------------

void AFuryDirector::BeginViewer()
{
	UWorld* World = GetWorld();

	// Daylight studio: sun, sky and a big floor.
	ADirectionalLight* Sun = World->SpawnActor<ADirectionalLight>(FVector::ZeroVector, FRotator(-48.f, 35.f, 0.f));
	Sun->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	Sun->GetLightComponent()->SetIntensity(6.f);
	Cast<UDirectionalLightComponent>(Sun->GetLightComponent())->SetAtmosphereSunLight(true);
	SceneActors.Add(Sun);
	SceneActors.Add(World->SpawnActor<ASkyAtmosphere>());

	ASkyLight* SkyLight = World->SpawnActor<ASkyLight>();
	SkyLight->GetLightComponent()->SetMobility(EComponentMobility::Movable);
	SkyLight->GetLightComponent()->SetRealTimeCapture(true);
	SkyLight->GetLightComponent()->SetIntensity(1.2f);
	SceneActors.Add(SkyLight);

	if (UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane")))
	{
		AStaticMeshActor* Floor = World->SpawnActor<AStaticMeshActor>();
		Floor->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		Floor->GetStaticMeshComponent()->SetStaticMesh(Plane);
		Floor->SetActorScale3D(FVector(80.f, 80.f, 1.f));
		SceneActors.Add(Floor);
	}

	// A football, dressed the same way the match dresses it.
	Stadium = World->SpawnActor<AFuryStadium>(AFuryStadium::StaticClass(), FTransform::Identity);
	Stadium->PrepareMaterials();
	BallMesh = Stadium->AddMesh(TEXT("SM_Football"), FVector::ZeroVector, 0.f);

	AFuryAthlete* Athlete = SpawnAthlete();
	Athletes.Add(Athlete);
	FString HomeId;
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryHome="), HomeId))
	{
		TeamPick[0] = FMath::Max(0, Fury::Teams().IndexOfByPredicate([&HomeId](const FFuryTeam& T) { return T.Id == HomeId; }));
	}
	int32 Roster = 0;
	FParse::Value(FCommandLine::Get(), TEXT("FuryRoster="), Roster);
	Athlete->SetLook(MakeLook(FParse::Param(FCommandLine::Get(), TEXT("FuryAwayKit")) ? 1 : 0, FMath::Clamp(Roster, 0, 14)));

	if (!ViewerOnly.IsEmpty())
	{
		for (int32 i = 0; i < AnimSet.Clips.Num(); ++i)
		{
			if (AnimSet.Clips[i].Name == FName(*ViewerOnly))
			{
				ViewerClip = i;
			}
		}
	}
}

void AFuryDirector::TickViewer(float DeltaTime)
{
	if (Athletes.Num() == 0 || AnimSet.Clips.Num() == 0)
	{
		ViewerText = TEXT("NO CLIPS");
		SetCamera(FVector(420.f, 260.f, 170.f), FVector(0.f, 0.f, 100.f), 40.f);
		return;
	}
	const FFuryPad& Keys = FFuryInput::Get().Pad(FFuryInput::KeyboardB);
	const FFuryClip& Clip = AnimSet.Clips[ViewerClip];
	ViewerTime += DeltaTime;
	const float Hold = FMath::Max(Clip.Length * 2.f, 1.6f);
	const bool bNext = Keys.NavX > 0 || (ViewerOnly.IsEmpty() && ViewerTime > Hold);
	if (bNext || Keys.NavX < 0)
	{
		ViewerClip = (ViewerClip + (bNext ? 1 : AnimSet.Clips.Num() - 1)) % AnimSet.Clips.Num();
		ViewerTime = 0.f;
	}
	const float Time = Clip.bLoop ? ViewerTime : FMath::Fmod(ViewerTime, Clip.Length + 0.4f);
	Athletes[0]->SetActorLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);
	Athletes[0]->PreviewClip(Clip.Name, Time);
	ViewerText = FString::Printf(TEXT("%s   %02d / %02d"), *Clip.Name.ToString().ToUpper(), FMath::Min(FMath::FloorToInt32(Time * 30.f), Clip.NumFrames - 1), Clip.NumFrames - 1);
	if (BallMesh)
	{
		// Show the football wherever this clip's grip puts it.
		BallMesh->SetVisibility(Clip.Grip != EFuryGrip::None);
		const FTransform Socket = Athletes[0]->GripWorld(Clip.Grip == EFuryGrip::None ? EFuryGrip::Hand : Clip.Grip);
		BallMesh->SetWorldLocationAndRotation(Socket.GetLocation(), Socket.GetRotation());
	}

	// The athlete faces +X; swing slowly around the front.
	Orbit += DeltaTime * 0.35f;
	float Distance = 520.f, Height = 170.f, Target = 100.f;
	FParse::Value(FCommandLine::Get(), TEXT("FuryViewDist="), Distance);
	FParse::Value(FCommandLine::Get(), TEXT("FuryViewHeight="), Height);
	FParse::Value(FCommandLine::Get(), TEXT("FuryViewTarget="), Target);
	const float Angle = 0.6f * FMath::Sin(Orbit) + 0.5f;
	SetCamera(FVector(FMath::Cos(Angle) * Distance, FMath::Sin(Angle) * Distance, Height), FVector(0.f, 0.f, Target), 40.f);
}

// ---------------------------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------------------------

static FString ReportFrameTimes(const TCHAR* Group, TArray<float>& Frames)
{
	if (Frames.IsEmpty()) { return FString(); }
	Frames.Sort();
	double TotalMs = 0.0;
	int32 LongFrames = 0;
	for (float Ms : Frames)
	{
		TotalMs += Ms;
		if (Ms > 12.5f) { ++LongFrames; }
	}
	auto Percentile = [&Frames](float P)
	{
		return Frames[FMath::CeilToInt(P * Frames.Num()) - 1];
	};
	const FString Line = FString::Printf(TEXT("FURY_BENCH %s frames=%d seconds=%.2f fps=%.2f p50_ms=%.3f p95_ms=%.3f p99_ms=%.3f max_ms=%.3f over12_5ms=%d"),
		Group, Frames.Num(), TotalMs / 1000.0, Frames.Num() * 1000.0 / TotalMs,
		Percentile(0.50f), Percentile(0.95f), Percentile(0.99f), Frames.Last(), LongFrames);
	UE_LOG(LogFury, Log, TEXT("%s"), *Line);
	return Line + LINE_TERMINATOR;
}

void AFuryDirector::FinishAudioCapture()
{
	if (AudioOut.IsEmpty()) { return; }
	const FString File = FPaths::ConvertRelativePathToFull(AudioOut);
	AudioOut.Reset();
	if (Audio::FMixerDevice* Mixer = FAudioDeviceManager::GetAudioMixerDeviceFromWorldContext(this))
	{
		float Channels = 0.f, Rate = 0.f;
		const Audio::FAlignedFloatBuffer& Samples = Mixer->StopRecording(nullptr, Channels, Rate);
		if (Samples.Num() > 0 && Channels > 0.f && Rate > 0.f)
		{
			// Finish the WAV before process exit, including the last play and its whistle.
			const Audio::TSampleBuffer<int16> PCM(Samples, Channels, Rate);
			Audio::FSoundWavePCMWriter Writer;
			if (Writer.SynchronouslyWriteToWavFile(PCM, FPaths::GetBaseFilename(File), FPaths::GetPath(File))) { return; }
		}
	}
	UE_LOG(LogFury, Error, TEXT("Could not finish audio capture: %s"), *File);
}

void AFuryDirector::TickHarness(float DeltaTime)
{
	RunTime += DeltaTime;
	if (PriorAudioTick != INDEX_NONE)
	{
		if (FAudioDevice* Device = GetWorld()->GetAudioDeviceRaw(); Device && Device->IsNonRealtime())
		{
			auto* Platform = static_cast<Audio::FMixerDevice*>(Device)->GetAudioMixerPlatform();
			if (Platform && Platform->GetPlatformApi() == TEXT("NonRealtime"))
			{
				static_cast<Audio::FMixerPlatformNonRealtime*>(Platform)->RenderAudio(DeltaTime);
			}
		}
	}
	if (bBenchmark)
	{
		const double Now = FPlatformTime::Seconds();
		if (BenchmarkLastFrame == 0.0) { BenchmarkStart = Now; }
		if (BenchmarkLastFrame - BenchmarkStart >= 5.0 && Screen == EFuryScreen::Match)
		{
			const float Ms = static_cast<float>((Now - BenchmarkLastFrame) * 1000.0);
			BenchmarkFrames.Add(Ms);
			if (bLastFrameLive) { BenchmarkLive.Add(Ms); }
			const double GpuMs = FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles());
			// Metal can return a discontinuous sample longer than the entire run.
			if (GpuMs > 0.0 && GpuMs <= (Now - BenchmarkStart) * 1000.0) { BenchmarkGPU.Add(GpuMs); }
		}
		BenchmarkLastFrame = Now;
		bLastFrameLive = Screen == EFuryScreen::Match && Sim.Phase == EFuryPhase::Live && !bPaused;
	}
	if (!ShotDir.IsEmpty() && ShotEvery > 0.f && RunTime >= ShotFrom)
	{
		ShotTimer += DeltaTime;
		if (ShotTimer >= ShotEvery)
		{
			ShotTimer = 0.f;
			const FString File = FPaths::ConvertRelativePathToFull(ShotDir / FString::Printf(TEXT("shot_%03d.png"), ShotIndex++));
			FScreenshotRequest::RequestScreenshot(File, true, false);
		}
	}
	// Frame-time report every five seconds: the average, and the single worst frame.
	++FrameCount;
	PerfTimer += DeltaTime;
	PerfWorst = FMath::Max(PerfWorst, DeltaTime);
	if (PerfTimer >= 5.f)
	{
		UE_LOG(LogFury, Log, TEXT("FURY_PERF avg %.2f ms (%.0f fps), worst %.1f ms, screen %d"), PerfTimer / FrameCount * 1000.f, FrameCount / PerfTimer, PerfWorst * 1000.f, static_cast<int32>(Screen));
		FrameCount = 0;
		PerfTimer = 0.f;
		PerfWorst = 0.f;
	}
	if (QuitAfter > 0.f && RunTime >= QuitAfter)
	{
		FinishAudioCapture();
		if (bBenchmark)
		{
			FString Report = FString::Printf(TEXT("Viewport %d x %d, field %.0f%%, cap %d FPS, preset %s%s"),
				OutputSize.X, OutputSize.Y, RenderPercent, Options.FrameCap(), *Options.Display(EFuryOption::Preset), LINE_TERMINATOR);
			Report += ReportFrameTimes(TEXT("match"), BenchmarkFrames);
			Report += ReportFrameTimes(TEXT("live"), BenchmarkLive);
			Report += ReportFrameTimes(TEXT("gpu"), BenchmarkGPU);
			FString Filename;
			if (FParse::Value(FCommandLine::Get(), TEXT("FuryBenchReport="), Filename))
			{
				FFileHelper::SaveStringToFile(Report, *Filename, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
			}
		}
		QuitAfter = 0.f;
		FPlatformMisc::RequestExit(false);
	}
}

void AFuryDirector::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	FFuryInput::Get().Tick(DeltaTime);
	ScreenTime += DeltaTime;
	UpdateFrameMeter();
	if (SettingsPad != INDEX_NONE || QuitPad != INDEX_NONE)
	{
		if (bPaused) { Banner.Start += DeltaTime; }
		else { TickBackdrop(DeltaTime, 5200.f, 2300.f, 0.07f); }
		if (QuitPad != INDEX_NONE) { TickQuitPrompt(); }
		else { TickSettings(); }
	}
	else switch (Screen)
	{
	case EFuryScreen::Viewer: TickViewer(DeltaTime); break;
	case EFuryScreen::Title: TickTitle(DeltaTime); break;
	case EFuryScreen::Lobby: TickLobby(DeltaTime); break;
	case EFuryScreen::Teams: TickTeams(DeltaTime); break;
	case EFuryScreen::Match: TickMatch(DeltaTime); break;
	case EFuryScreen::Final: TickFinal(DeltaTime); break;
	}
	if (bPinnedCamera) { SetCamera(PinnedEye, PinnedLook, PinnedFov); }
	// On taller displays, upscale the 3D field and keep the HUD at display resolution.
	if (GEngine && GEngine->GameViewport)
	{
		FVector2D Size;
		GEngine->GameViewport->GetViewportSize(Size);
		OutputSize = FIntPoint(FMath::RoundToInt32(Size.X), FMath::RoundToInt32(Size.Y));
		if (Size.Y > 1.f && OutputSize.Y != SizedFor)
		{
			SizedFor = FMath::RoundToInt32(Size.Y);
			float Percent = Options.ScreenPercent(SizedFor);
			bFixedRenderOverride = FParse::Value(FCommandLine::Get(), TEXT("FuryScreenPct="), Percent);
			AutoScale.Reset();
			if (IConsoleVariable* Variable = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
			{
				Variable->Set(Percent, ECVF_SetByCode);
				RenderPercent = Variable->GetFloat();
			}
			UE_LOG(LogFury, Log, TEXT("Window %d x %d: rendering at %.0f%%"), FMath::RoundToInt32(Size.X), SizedFor, Percent);
		}
		else if (Screen == EFuryScreen::Match && Sim.Phase == EFuryPhase::Live && !bPaused && !bFixedRenderOverride && Options.Get(EFuryOption::RenderScale) == 0)
		{
			const int32 Cap = Options.FrameCap();
			const float BudgetMs = 1000.f / (Cap > 0 ? FMath::Min(Cap, 120) : 120);
			const float Next = AutoScale.Sample(DeltaTime, FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()), BudgetMs, RenderPercent, Options.ScreenPercent(SizedFor));
			if (Next != RenderPercent)
			{
				static IConsoleVariable* Scale = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"));
				if (Scale) { Scale->Set(Next, ECVF_SetByCode); RenderPercent = Scale->GetFloat(); }
			}
		}
	}
	if (Audio)
	{
		Audio->Tick(DeltaTime, bPaused ? 0.f : Excitement);
	}
	if (!bPaused) { Effects.Tick(DeltaTime, Camera->GetForwardVector(), Camera->GetRightVector()); }
	TickHarness(DeltaTime);
}
