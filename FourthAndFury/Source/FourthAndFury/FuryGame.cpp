#include "FuryGame.h"

#include "Engine/Engine.h"
#include "Engine/World.h"
#include "FuryDirector.h"
#include "FuryHUD.h"
#include "FuryTypes.h"

DEFINE_LOG_CATEGORY(LogFury);

AFuryGameMode::AFuryGameMode()
{
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AFuryPlayerController::StaticClass();
	HUDClass = AFuryHUD::StaticClass();
}

void AFuryGameMode::StartPlay()
{
	// No engine debug text over the game ("Preparing shaders", "Lighting needs to be rebuilt"...).
	GAreScreenMessagesEnabled = false;
	Director = GetWorld()->SpawnActor<AFuryDirector>(AFuryDirector::StaticClass(), FTransform::Identity);
	Super::StartPlay();
}

AFuryPlayerController::AFuryPlayerController()
{
	bShowMouseCursor = false;
	bAutoManageActiveCameraTarget = false;
}

void AFuryPlayerController::BeginPlay()
{
	Super::BeginPlay();
	FInputModeGameOnly Mode;
	Mode.SetConsumeCaptureMouseDown(false);
	SetInputMode(Mode);
}
