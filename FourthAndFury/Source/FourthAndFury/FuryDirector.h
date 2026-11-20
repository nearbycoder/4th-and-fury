#pragma once

#include "CoreMinimal.h"
#include "FuryAnim.h"
#include "FuryBot.h"
#include "FuryFX.h"
#include "FuryFilm.h"
#include "FuryOptions.h"
#include "FurySim.h"
#include "FuryShadows.h"
#include "FuryTypes.h"
#include "GameFramework/Actor.h"
#include "FuryDirector.generated.h"

class AFuryAthlete;
class AFuryStadium;
class UFuryAudio;
class UCameraComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class USkeletalMesh;
class UStaticMeshComponent;
class UTexture;
struct FFuryPad;

enum class EFuryScreen : uint8 { Viewer, Title, Lobby, Teams, Match, Final };

/** A line of big type that slides in over the action. */
struct FFuryBanner
{
	FString Title, Detail;
	FLinearColor Color = FLinearColor::White;
	float Start = -100.f;      // real-time seconds
	float Length = 2.f;
	bool bBig = false;
};

/** One of the eight places at the table. */
struct FFuryLobbySeat
{
	bool bJoined = false;
	int32 Pad = INDEX_NONE;    // index into FFuryInput's pads
	int32 Side = INDEX_NONE;   // -1 undecided, 0 home (left), 1 away (right)
	bool bReady = false;
	bool bBot = false;
};

/**
 * Runs the whole game inside one level: it owns the camera, the athletes, the stadium and the
 * flow from title screen to final whistle. The HUD reads its state to draw the interface.
 */
UCLASS()
class AFuryDirector : public AActor
{
	GENERATED_BODY()

public:
	AFuryDirector();
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	// --- State the HUD draws from ---
	EFuryScreen Screen = EFuryScreen::Title;
	float ScreenTime = 0.f;
	FFurySim Sim;
	FFuryFilmRecorder Film;
	bool bViewingFilm = false, bFilmRolling = false;
	float FilmTime = 0.f;
	const FFuryPlayFilm& SelectedFilm() const { return Screen == EFuryScreen::Final && Film.LongestTouchdown.Ready() ? Film.LongestTouchdown : Film.Last; }
	FFuryLobbySeat Seats[Fury::MaxSeats];
	int32 TeamPick[2] = { 0, 1 };
	bool bTeamLocked[2] = { false, false };
	int32 OptionRow[2] = { 0, 0 };          // 0 team, 1 quarter length, 2 difficulty
	int32 QuarterChoice = 2;                // index into QuarterOptions
	int32 SkillChoice = 1;                  // 0 rookie, 1 pro, 2 all-fury
	float StartCountdown = -1.f;
	bool bPaused = false;
	bool bFieldGuide = false;
	int32 PauseCursor = 0;
	bool bConfirmPauseAction = false;
	int32 PauseSeat = INDEX_NONE;
	FFuryOptions Options;
	int32 SettingsPad = INDEX_NONE;
	int32 QuitPad = INDEX_NONE;
	bool bSoundTab = false;
	int32 SettingsRow = 0;
	float LiveFPS = 0.f, RenderPercent = 100.f;
	FIntPoint OutputSize = FIntPoint::ZeroValue;
	bool bDemo = false;
	bool bQuickMatch = false;
	FFuryBanner Banner;
	float Excitement = 0.2f;                // 0 murmur .. 1 bedlam

	bool IsViewer() const { return Screen == EFuryScreen::Viewer; }
	FString ViewerLabel() const { return ViewerText; }
	const FFuryAnimSet& Anims() const { return AnimSet; }
	AFuryAthlete* Athlete(int32 Index) const { return Athletes.IsValidIndex(Index) ? Athletes[Index].Get() : nullptr; }
	AFuryStadium* GetStadium() const { return Stadium; }
	UFuryAudio* GetAudio() const { return Audio; }
	UTexture* TeamLogo(int32 League) const;
	UTexture* UiTexture(const TCHAR* Name) const;
	const FFuryPad* SeatPad(int32 Seat) const;
	int32 NumJoined() const;
	int32 NumOnSide(int32 Side) const;
	int32 Picker(int32 Side) const;          // seat that chooses the team for a side
	float QuarterSeconds() const;
	float Skill() const;
	static FLinearColor SeatColor(int32 Seat);
	static const TCHAR* SkillName(int32 Choice);

private:
	// --- Shared setup ---
	void OpenSettings(int32 Pad);
	void TickSettings();
	void TickQuitPrompt();
	void ApplyGraphics();
	void UpdateFrameMeter();
	double MeterStart = 0.0, MeterLast = 0.0;
	int32 MeterFrames = 0;
	void LoadAssets();
	AFuryAthlete* SpawnAthlete();
	void SetCamera(const FVector& Eye, const FVector& Target, float FieldOfView);
	void GoTo(EFuryScreen NewScreen);
	void ShowBanner(const FString& Title, const FString& Detail, const FLinearColor& Color, float Length, bool bBig);

	// --- Front end ---
	bool TryJoinFromTitle();
	void TickTitle(float DeltaTime);
	void TickLobby(float DeltaTime);
	void TickTeams(float DeltaTime);
	void TickFinal(float DeltaTime);
	void TickBackdrop(float DeltaTime, float Radius, float Height, float Speed);
	void ShowcaseAthletes(bool bShow);

	// --- The match (FuryDirectorMatch.cpp) ---
	void StartMatch();
	void TickMatch(float DeltaTime);
	void TickPause(float DeltaTime);
	void OpenFilm(int32 Seat);
	void TickFilm(const FFuryPad& Pad, float DeltaTime);
	void GatherInput(FFurySeatInput* Out, float DeltaTime);
	void HandleEvents();
	void DressTeams();
	void UpdateAthletes(float DeltaTime);
	void UpdateBall(float DeltaTime);
	void UpdateMarkers();
	void UpdateCamera(float DeltaTime, bool bSnap);
	void UpdateEffects(float DeltaTime);
	struct FFuryLook MakeLook(int32 Team, int32 Roster) const;

	// --- Animation viewer (-FuryViewer) ---
	void BeginViewer();
	void TickViewer(float DeltaTime);

	// --- Test harness: timed screenshots and auto-quit ---
	void TickHarness(float DeltaTime);
	void FinishAudioCapture();

	UPROPERTY()
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY()
	TObjectPtr<USkeletalMesh> BodyMeshes[3];

	UPROPERTY()
	TObjectPtr<UMaterialInterface> AthleteMaterial;

	/** The fourteen athletes on the field right now, by simulation slot. */
	UPROPERTY()
	TArray<TObjectPtr<AFuryAthlete>> Athletes;

	/** Every member of both rosters, dressed once per match; units change by swapping who is shown. */
	UPROPERTY()
	TArray<TObjectPtr<AFuryAthlete>> Squad;

	UPROPERTY()
	TArray<TObjectPtr<AActor>> SceneActors;

	UPROPERTY()
	TObjectPtr<AFuryStadium> Stadium;

	UPROPERTY()
	TObjectPtr<UFuryAudio> Audio;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> BallMesh;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> TeeMesh;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Markers;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> CatchMarker;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> MarkerMaterials;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> ScrimmageLine;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> FirstDownLine;

	UPROPERTY()
	mutable TMap<FString, TObjectPtr<UTexture>> Textures;

	FFuryAnimSet AnimSet;
	FFuryFX Effects;
	FFuryShadows Shadows;
	FFuryBot Bots[Fury::MaxSeats];
	float TrailDistance = 0.f;
	TOptional<FVector> LastTrailPoint;
	float FireworkTimer = 0.f;
	int32 FireworksLeft = 0;
	int32 FireworkTeam = 0;
	float FlashTimer = 0.f;
	FRandomStream Sparkle;
	static constexpr int32 RosterSize = 15;
	int32 SquadLeague[2] = { -1, -1 };
	int32 DressedLeague[2] = { -1, -1 };
	int32 SizedFor = 0;
	FFuryAutoScale AutoScale;
	bool bFixedRenderOverride = false;

	// Camera
	FVector CamEye = FVector(0.f, 4500.f, 2400.f), CamLook = FVector::ZeroVector;
	float CamFov = 36.f;
	float Shake = 0.f;
	float Orbit = 0.f;
	float HitStop = 0.f, SlowMo = 0.f;
	float TimeScale = 1.f;
	float FinalDelay = 0.f;
	float IdleTime = 0.f;

	// What was last seen, so sounds fire on changes.
	EFuryPhase HeardPhase = EFuryPhase::GameOver;
	FFuryPick HeardPick[2];
	int32 HeardPat = 0, HeardSecond = 0;
	float HeardMeter = 0.f, HeardMeterStep = 0.f;
	bool bSaidWinner = false;
	void TickMatchSounds(float DeltaTime);
	bool TickCountdown(float Length, float DeltaTime);
	FRotator BallSpin = FRotator::ZeroRotator;
	EFuryBallState LastDrawnBall = EFuryBallState::Dead;
	FVector ReleaseOffset = FVector::ZeroVector, CatchOffset = FVector::ZeroVector;
	float CatchBlend = 0.f;

	// Viewer
	int32 ViewerClip = 0;
	float ViewerTime = 0.f;
	FString ViewerText;
	FString ViewerOnly;

	// Harness
	FString ShotDir, AudioOut;
	int32 PriorAudioTick = INDEX_NONE;
	double PriorCaptureDelta = 0.0;
	float ShotEvery = 0.f, ShotFrom = 0.f, ShotTimer = 0.f, QuitAfter = 0.f, RunTime = 0.f;
	int32 ShotIndex = 0;
	bool bBenchmark = false;
	bool bTestPause = false, bPinnedCamera = false;
	FVector PinnedEye = FVector::ZeroVector, PinnedLook = FVector::ZeroVector;
	float PinnedFov = 40.f;
	int32 SoakMatches = 0, SoakFinished = 0;
	double BenchmarkLastFrame = 0.0, BenchmarkStart = 0.0;
	bool bLastFrameLive = false;
	TArray<float> BenchmarkFrames, BenchmarkLive, BenchmarkGPU;
	int32 FrameCount = 0;
	float PerfTimer = 0.f, PerfWorst = 0.f;
};
