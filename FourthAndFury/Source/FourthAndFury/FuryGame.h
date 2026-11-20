#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "FuryGame.generated.h"

class AFuryDirector;

/** Spawns the director, which runs the whole game inside one level. */
UCLASS()
class AFuryGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AFuryGameMode();
	virtual void StartPlay() override;

	UPROPERTY()
	TObjectPtr<AFuryDirector> Director;
};

/** The single local controller: it only owns the view and the HUD. Input comes through FFuryInput. */
UCLASS()
class AFuryPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AFuryPlayerController();
	virtual void BeginPlay() override;
};
