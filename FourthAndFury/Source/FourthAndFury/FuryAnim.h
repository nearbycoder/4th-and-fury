#pragma once

#include "CoreMinimal.h"
#include "FuryTypes.h"

class UAnimSequence;
class USkeletalMesh;

/**
 * Animation for the athletes without an animation blueprint.
 *
 * Every clip authored in Blender is sampled once at load into plain arrays of local bone
 * transforms. Athletes then build each frame's pose themselves by sampling and blending those
 * arrays, and write the result straight into a poseable mesh. That keeps the whole animation
 * state machine in ordinary game code.
 */
struct FFuryPose
{
	static constexpr int32 MaxBones = 64;

	FQuat4f Rot[MaxBones];
	FVector3f Loc[MaxBones];

	/** this = lerp(this, Other, Alpha) for bones [0, Num). */
	void BlendTo(const FFuryPose& Other, float Alpha, int32 Num);
	/** Same, with a per-bone weight multiplied into Alpha. */
	void BlendToMasked(const FFuryPose& Other, float Alpha, const float* Mask, int32 Num);
};

struct FFuryClip
{
	FName Name;
	int32 NumFrames = 0;        // samples, 30 per second, first and last inclusive
	float Length = 0.f;         // seconds
	bool bLoop = false;
	float Speed = 0.f;          // ground speed (cm/s) at which a locomotion loop does not skate
	EFuryGrip Grip = EFuryGrip::None;
	TMap<FName, float> Events;  // event name -> seconds
	TArray<FQuat4f> Rot;        // NumFrames * NumBones
	TArray<FVector3f> Loc;

	void Sample(float Time, FFuryPose& Out, int32 NumBones) const;
	float Event(FName EventName, float Fallback) const;
};

/** Every clip plus the skeleton they animate. One instance is shared by all athletes. */
class FFuryAnimSet
{
public:
	/** Loads the skeleton from Mesh and bakes every animation sequence under AnimPath. */
	bool Build(USkeletalMesh* Mesh, const FString& AnimPath, const FString& ManifestFile);

	const FFuryClip* Find(FName Name) const;
	/** The first of the given clips that exists (for graceful fallbacks while art is in progress). */
	const FFuryClip* FindFirst(std::initializer_list<const TCHAR*> Names) const;
	int32 Bone(FName Name) const;

	int32 NumBones = 0;
	TArray<FName> BoneNames;
	TArray<int32> Parents;
	FFuryPose RefPose;
	TArray<FFuryClip> Clips;

	/** Per-bone weights: 1 from the upper spine up (arms, neck, head), 0 for hips and legs. */
	float UpperBody[FFuryPose::MaxBones];
	/** Per-bone weights for the left arm only. */
	float LeftArm[FFuryPose::MaxBones];
	float CarryArm[FFuryPose::MaxBones];

	// Frequently used bones.
	int32 Pelvis = INDEX_NONE, Spine1 = INDEX_NONE, Spine2 = INDEX_NONE, Spine3 = INDEX_NONE, Head = INDEX_NONE;
	int32 HandR = INDEX_NONE, HandL = INDEX_NONE, BallHand = INDEX_NONE, BallTuck = INDEX_NONE;
	int32 FootL = INDEX_NONE, FootR = INDEX_NONE, ToeL = INDEX_NONE, ToeR = INDEX_NONE, Towel = INDEX_NONE;
	int32 UpperArmL = INDEX_NONE, UpperArmR = INDEX_NONE;

private:
	void Bake(UAnimSequence* Sequence, FFuryClip& Clip) const;
	void LoadManifest(const FString& ManifestFile);
	static TArray<FString> ManifestNames(const FString& ManifestFile);
	TMap<FName, int32> ClipIndex;
};
