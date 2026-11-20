#pragma once

#include "CoreMinimal.h"
#include "FuryTeams.h"
#include "GameFramework/Actor.h"
#include "FuryStadium.generated.h"

class UExponentialHeightFogComponent;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class USkyLightComponent;
class USpotLightComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UTexture;
class UTextureRenderTarget2D;

/**
 * The arena: turf, the bowl and its props, the crowd, the floodlights and the night sky.
 *
 * Everything is assembled in code from the meshes and data the Blender scripts export
 * (Content/Fury/Stadium, Content/Data/stadium_meta.json, Content/Data/crowd.bin).
 */
UCLASS()
class AFuryStadium : public AActor
{
	GENERATED_BODY()

public:
	AFuryStadium();

	/** Builds the scene. Safe to call once; Dress() re-colours it for a matchup. */
	void Build();
	void SetLightingQuality(int32 Level);
	/** Loads the base materials only (enough for AddMesh), without building the arena. */
	void PrepareMaterials();
	/** Team colours on seats, wall pads, end zones, the midfield emblem and the crowd. */
	void Dress(const FFuryTeam& Home, const FFuryTeam& Away);
	/** 0 = murmur, 1 = bedlam: drives how much the crowd bounces. */
	void SetExcitement(float Value);
	void SetChains(int32 Down, float Line, float Target, float Direction, bool bGoalToGo);

	/** Adds one of the exported stadium meshes (dressed in its slot materials) to the scene. */
	UStaticMeshComponent* AddMesh(const TCHAR* MeshName, const FVector& Location, float YawDegrees);

	UTextureRenderTarget2D* BoardTarget() const { return Board; }
	/** World position of the centre of the big video board, for cutaway shots. */
	FVector BoardCentre() const { return BoardWorld; }
	/** A sample of spectator positions (for camera flashes in the stands). */
	const TArray<FVector>& SeatSample() const { return Seats; }

private:
	void ApplySlotMaterials(UStaticMeshComponent* Component);
	UMaterialInstanceDynamic* Surface(const FLinearColor& Color, float Roughness, float Metallic = 0.f, float Detail = 0.f, float Grime = 0.f, float Tiling = 1.f);
	void BuildCrowd();
	void BuildLights(const TSharedPtr<class FJsonObject>& Meta);
	void BuildProps(const TSharedPtr<class FJsonObject>& Meta);
	UTexture* LoadTexture(const FString& Name) const;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Field;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Bowl;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> SkyDome;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Props;
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> ChainPoles;
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> DownBox;
	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> DownFace;
	UPROPERTY()
	TArray<TObjectPtr<UTexture>> DownDigits;
	int32 ShownDown = 0;
	float ShownLine = 0.f, ShownTarget = 0.f, ShownDirection = 0.f;
	bool bShownGoal = false;

	UPROPERTY()
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> Crowd;

	UPROPERTY()
	TArray<TObjectPtr<USpotLightComponent>> Lights;

	UPROPERTY()
	TObjectPtr<USkyLightComponent> SkyLight;

	UPROPERTY()
	TObjectPtr<UExponentialHeightFogComponent> Fog;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> SurfaceBase;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> GlowBase;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> FieldMaterial;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> CrowdMaterial;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> SeatA;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> SeatB;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> WallPad;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> GoalPad;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;

	UPROPERTY()
	TObjectPtr<UTextureRenderTarget2D> Board;

	TArray<FVector> Seats;
	FVector BoardWorld = FVector(0.f, -5600.f, 2900.f);
	bool bBuilt = false;
};
