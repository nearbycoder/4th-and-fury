#pragma once

#include "CoreMinimal.h"
#include "FuryAnim.h"
#include "FuryTypes.h"
#include "GameFramework/Actor.h"
#include "FuryAthlete.generated.h"

class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPoseableMeshComponent;
class USkeletalMesh;
class UTexture;

/** How one athlete is dressed. */
struct FFuryLook
{
	EFuryBuild Build = EFuryBuild::Mid;
	FLinearColor Jersey = FLinearColor::Red;
	FLinearColor JerseyTrim = FLinearColor::White;
	FLinearColor NumberFill = FLinearColor::White;
	FLinearColor NumberEdge = FLinearColor::Black;
	FLinearColor Pants = FLinearColor::White;
	FLinearColor PantsStripe = FLinearColor::Red;
	FLinearColor Helmet = FLinearColor::Red;
	FLinearColor HelmetStripe = FLinearColor::White;
	FLinearColor Facemask = FLinearColor(0.6f, 0.6f, 0.62f);
	FLinearColor Socks = FLinearColor::White;
	FLinearColor Shoes = FLinearColor(0.02f, 0.02f, 0.02f);
	FLinearColor Gloves = FLinearColor::White;
	FLinearColor Skin = FLinearColor(0.45f, 0.28f, 0.18f);
	int32 Number = 1;
	bool bVisor = false;
	float Scale = 1.f;
	UTexture* Logo = nullptr;
};

/** What the simulation tells an athlete each frame. */
struct FFuryAthleteState
{
	FVector2D Pos = FVector2D::ZeroVector;
	float Height = 0.f;          // extra lift from the simulation (being launched by a hit)
	float Yaw = 0.f;             // facing, radians, 0 = +X
	FVector2D Vel = FVector2D::ZeroVector;
	EFuryAct Act = EFuryAct::Stand;
	uint8 Variant = 0;
	int32 ActSerial = 0;         // changes whenever a new action starts
	float ActTime = 0.f;         // seconds since the action started
	float ActLength = 0.f;       // how long the simulation gives the action (0 = open-ended)
	float ActKey = 0.f;          // when its key moment (release, contact) happens in the simulation
	bool bHasBall = false;
	bool bPasser = false;        // holding the ball to throw
	bool bFury = false;
	bool bVisible = true;
};

UCLASS()
class AFuryAthlete : public AActor
{
	GENERATED_BODY()

public:
	AFuryAthlete();

	void Setup(const FFuryAnimSet* InAnims, USkeletalMesh* LeanMesh, USkeletalMesh* MidMesh, USkeletalMesh* BigMesh, UMaterialInterface* BodyMaterial);
	void SetLook(const FFuryLook& Look);

	/** Moves, poses and renders the athlete for this frame. */
	void Advance(const FFuryAthleteState& State, float DeltaTime);

	/** Plays one named clip directly (viewer / presentation use). */
	void PreviewClip(FName ClipName, float Time);

	/** World transform of a bone as posed this frame. */
	FTransform BoneWorld(int32 Bone) const;
	/** Where the ball sits for the grip the current animation uses (None when it is not held). */
	EFuryGrip CurrentGrip() const { return Grip; }
	FTransform GripWorld(EFuryGrip InGrip) const;
	FVector HeadWorld() const;
	bool Stepped() const { return bStepped; }

	UPoseableMeshComponent* GetMesh() const { return Mesh; }

private:
	struct FLayer
	{
		const FFuryClip* Clip = nullptr;
		bool bUpperOnly = false;
		bool bLeftArmOnly = false;
	};

	void BuildPose(const FFuryAthleteState& State, float DeltaTime, FFuryPose& Out);
	void Locomotion(const FFuryAthleteState& State, float DeltaTime, FFuryPose& Out);
	FLayer ActionFor(const FFuryAthleteState& State) const;
	const FFuryClip* StanceFor(const FFuryAthleteState& State) const;
	void Apply(const FFuryPose& Pose, bool bPlant = false);
	void PlantFoot(int32 Side, int32 Toe, TArray<FTransform>& Local);
	TOptional<FVector> FootAnchor[2];
	float TowelAngle = 0.f, TowelVelocity = 0.f;
	bool bStepped = false;
	float ClipTime(const FFuryAthleteState& State, const FFuryClip& Clip) const;

	UPROPERTY()
	TObjectPtr<UPoseableMeshComponent> Mesh;

	UPROPERTY()
	TObjectPtr<USkeletalMesh> Meshes[3];

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;

	const FFuryAnimSet* Anims = nullptr;

	FFuryPose Current;                 // the pose shown last frame
	FFuryPose From;                    // pose captured when the action changed
	float BlendTime = 0.f, BlendLength = 0.f;
	int32 LastSerial = -1;
	EFuryAct LastAct = EFuryAct::Stand;
	bool bWasFullBody = false;
	float Phase = 0.f;                 // shared locomotion phase, 0..1
	float MoveBlend = 0.f;             // 0 standing, 1 moving
	float GaitBlend = 0.f;             // 0 jog, 1 sprint
	FVector2D DirBlend = FVector2D(1.f, 0.f);
	float Lean = 0.f;
	float LastYaw = 0.f;
	bool bPosed = false;
	bool bGlowing = false;
	float ArmSpread = 0.f;             // radians the upper arms are held out from the body (wide builds)
	EFuryGrip Grip = EFuryGrip::None;
	TArray<FTransform> ComponentSpace;
};
