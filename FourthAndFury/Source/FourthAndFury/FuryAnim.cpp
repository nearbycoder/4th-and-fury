#include "FuryAnim.h"

#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/FileHelper.h"
#include "ReferenceSkeleton.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	constexpr float BakeRate = 30.f;

	FQuat4f Nlerp(const FQuat4f& A, const FQuat4f& B, float Alpha)
	{
		// Shortest-arc normalized lerp: plenty accurate at 30 samples per second.
		const float Sign = (A | B) < 0.f ? -1.f : 1.f;
		FQuat4f Out(
			A.X + (B.X * Sign - A.X) * Alpha,
			A.Y + (B.Y * Sign - A.Y) * Alpha,
			A.Z + (B.Z * Sign - A.Z) * Alpha,
			A.W + (B.W * Sign - A.W) * Alpha);
		Out.Normalize();
		return Out;
	}
}

void FFuryPose::BlendTo(const FFuryPose& Other, float Alpha, int32 Num)
{
	if (Alpha <= 0.f)
	{
		return;
	}
	if (Alpha >= 1.f)
	{
		FMemory::Memcpy(Rot, Other.Rot, sizeof(FQuat4f) * Num);
		FMemory::Memcpy(Loc, Other.Loc, sizeof(FVector3f) * Num);
		return;
	}
	for (int32 i = 0; i < Num; ++i)
	{
		Rot[i] = Nlerp(Rot[i], Other.Rot[i], Alpha);
		Loc[i] = FMath::Lerp(Loc[i], Other.Loc[i], Alpha);
	}
}

void FFuryPose::BlendToMasked(const FFuryPose& Other, float Alpha, const float* Mask, int32 Num)
{
	if (Alpha <= 0.f)
	{
		return;
	}
	for (int32 i = 0; i < Num; ++i)
	{
		const float W = Alpha * Mask[i];
		if (W > 0.f)
		{
			Rot[i] = Nlerp(Rot[i], Other.Rot[i], W);
			Loc[i] = FMath::Lerp(Loc[i], Other.Loc[i], W);
		}
	}
}

void FFuryClip::Sample(float Time, FFuryPose& Out, int32 NumBones) const
{
	if (NumFrames <= 0)
	{
		return;
	}
	float Frame = Time * BakeRate;
	const int32 Last = NumFrames - 1;
	if (bLoop && Last > 0)
	{
		Frame = FMath::Fmod(Frame, static_cast<float>(Last));
		if (Frame < 0.f)
		{
			Frame += Last;
		}
	}
	else
	{
		Frame = FMath::Clamp(Frame, 0.f, static_cast<float>(Last));
	}
	const int32 A = FMath::Min(FMath::FloorToInt32(Frame), Last);
	const int32 B = FMath::Min(A + 1, Last);
	const float Alpha = Frame - A;
	const FQuat4f* RA = &Rot[A * NumBones];
	const FQuat4f* RB = &Rot[B * NumBones];
	const FVector3f* LA = &Loc[A * NumBones];
	const FVector3f* LB = &Loc[B * NumBones];
	for (int32 i = 0; i < NumBones; ++i)
	{
		Out.Rot[i] = Nlerp(RA[i], RB[i], Alpha);
		Out.Loc[i] = FMath::Lerp(LA[i], LB[i], Alpha);
	}
}

float FFuryClip::Event(FName EventName, float Fallback) const
{
	const float* Found = Events.Find(EventName);
	return Found ? *Found : Fallback;
}

bool FFuryAnimSet::Build(USkeletalMesh* Mesh, const FString& AnimPath, const FString& ManifestFile)
{
	Clips.Reset();
	ClipIndex.Reset();
	if (!Mesh)
	{
		UE_LOG(LogFury, Error, TEXT("Animation set: no skeletal mesh"));
		return false;
	}

	const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
	NumBones = FMath::Min(Ref.GetNum(), FFuryPose::MaxBones);
	BoneNames.SetNum(NumBones);
	Parents.SetNum(NumBones);
	const TArray<FTransform>& RefLocal = Ref.GetRefBonePose();
	for (int32 i = 0; i < NumBones; ++i)
	{
		BoneNames[i] = Ref.GetBoneName(i);
		Parents[i] = Ref.GetParentIndex(i);
		RefPose.Rot[i] = FQuat4f(RefLocal[i].GetRotation());
		RefPose.Loc[i] = FVector3f(RefLocal[i].GetTranslation());
	}

	Pelvis = Bone(TEXT("pelvis"));
	Spine1 = Bone(TEXT("spine_01"));
	Spine2 = Bone(TEXT("spine_02"));
	Spine3 = Bone(TEXT("spine_03"));
	Head = Bone(TEXT("head"));
	UpperArmL = Bone(TEXT("upperarm_l"));
	UpperArmR = Bone(TEXT("upperarm_r"));
	HandR = Bone(TEXT("hand_r"));
	HandL = Bone(TEXT("hand_l"));
	BallHand = Bone(TEXT("ball_hand_r"));
	BallTuck = Bone(TEXT("ball_tuck_r"));
	FootL = Bone(TEXT("foot_l"));
	FootR = Bone(TEXT("foot_r"));
	ToeL = Bone(TEXT("ball_l"));
	ToeR = Bone(TEXT("ball_r"));
	Towel = Bone(TEXT("towel"));

	// Masks: a bone inherits its parent's weight; the listed bones start a region.
	auto BuildMask = [this](float* Mask, std::initializer_list<const TCHAR*> Roots, float SoftRootWeight)
	{
		for (int32 i = 0; i < NumBones; ++i)
		{
			float W = Parents[i] >= 0 ? Mask[Parents[i]] : 0.f;
			for (const TCHAR* Root : Roots)
			{
				if (BoneNames[i] == FName(Root))
				{
					W = 1.f;
				}
			}
			Mask[i] = W;
		}
		// Ease the region in over the bone just below it so the seam does not snap.
		const int32 Soft = Bone(TEXT("spine_02"));
		if (SoftRootWeight > 0.f && Soft != INDEX_NONE && Mask[Soft] < SoftRootWeight)
		{
			Mask[Soft] = SoftRootWeight;
		}
	};
	FMemory::Memzero(UpperBody);
	FMemory::Memzero(LeftArm);
	FMemory::Memzero(CarryArm);
	BuildMask(UpperBody, { TEXT("spine_03") }, 0.5f);
	BuildMask(LeftArm, { TEXT("clavicle_l") }, 0.f);
	BuildMask(CarryArm, { TEXT("clavicle_r") }, 0.f);

	auto AddClip = [this](UAnimSequence* Sequence, const FString& Name)
	{
		if (!Sequence || ClipIndex.Contains(FName(*Name)))
		{
			return;
		}
		FFuryClip& Clip = Clips.AddDefaulted_GetRef();
		Clip.Name = FName(*Name);
		Bake(Sequence, Clip);
		ClipIndex.Add(Clip.Name, Clips.Num() - 1);
	};

	// The manifest names every clip, so load them by name: that works the same in the editor and in
	// a packaged game, where there is no folder to look through.
	for (const FString& Name : ManifestNames(ManifestFile))
	{
		UAnimSequence* Sequence = LoadObject<UAnimSequence>(nullptr, *FString::Printf(TEXT("%s/A_%s.A_%s"), *AnimPath, *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Sequence)
		{
			UE_LOG(LogFury, Warning, TEXT("Animation %s is in the manifest but not in %s"), *Name, *AnimPath);
		}
		AddClip(Sequence, Name);
	}
	// Then anything else under the path that the manifest does not mention.
	FAssetRegistryModule& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));
	Registry.Get().ScanPathsSynchronous({ AnimPath }, true);
	TArray<FAssetData> Assets;
	Registry.Get().GetAssetsByPath(FName(*AnimPath), Assets, true);
	for (const FAssetData& Asset : Assets)
	{
		FString Name = Asset.AssetName.ToString();
		Name.RemoveFromStart(TEXT("A_"));
		if (!ClipIndex.Contains(FName(*Name)))
		{
			AddClip(Cast<UAnimSequence>(Asset.GetAsset()), Name);
		}
	}
	LoadManifest(ManifestFile);
	UE_LOG(LogFury, Log, TEXT("Animation set: %d bones, %d clips from %s"), NumBones, Clips.Num(), *AnimPath);
	return Clips.Num() > 0;
}

void FFuryAnimSet::Bake(UAnimSequence* Sequence, FFuryClip& Clip) const
{
	const USkeleton* Skeleton = Sequence->GetSkeleton();
	const FReferenceSkeleton& SkelRef = Skeleton->GetReferenceSkeleton();
	Clip.Length = Sequence->GetPlayLength();
	Clip.NumFrames = FMath::Max(1, FMath::RoundToInt32(Clip.Length * BakeRate) + 1);
	Clip.Rot.SetNumUninitialized(Clip.NumFrames * NumBones);
	Clip.Loc.SetNumUninitialized(Clip.NumFrames * NumBones);

	// The mesh and the skeleton asset may order bones differently; go by name.
	TArray<int32> SkelIndex;
	SkelIndex.SetNum(NumBones);
	for (int32 i = 0; i < NumBones; ++i)
	{
		SkelIndex[i] = SkelRef.FindBoneIndex(BoneNames[i]);
	}

#if WITH_EDITOR
	const bool bRaw = true;    // exact source keys
#else
	const bool bRaw = false;   // cooked builds only carry compressed data
#endif
	for (int32 Frame = 0; Frame < Clip.NumFrames; ++Frame)
	{
		const double Time = FMath::Min(static_cast<double>(Frame) / BakeRate, static_cast<double>(Clip.Length));
		const FAnimExtractContext Context(Time);
		for (int32 i = 0; i < NumBones; ++i)
		{
			FTransform Atom(FQuat(RefPose.Rot[i]), FVector(RefPose.Loc[i]));
			if (SkelIndex[i] != INDEX_NONE)
			{
				Sequence->GetBoneTransform(Atom, FSkeletonPoseBoneIndex(SkelIndex[i]), Context, bRaw);
			}
			Clip.Rot[Frame * NumBones + i] = FQuat4f(Atom.GetRotation().GetNormalized());
			Clip.Loc[Frame * NumBones + i] = FVector3f(Atom.GetTranslation());
		}
	}
}

TArray<FString> FFuryAnimSet::ManifestNames(const FString& ManifestFile)
{
	TArray<FString> Names;
	FString Text;
	TSharedPtr<FJsonObject> Root;
	if (ManifestFile.IsEmpty() || !FFileHelper::LoadFileToString(Text, *ManifestFile)
		|| !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
	{
		return Names;
	}
	const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
	if (Root->TryGetArrayField(TEXT("clips"), Entries))
	{
		for (const TSharedPtr<FJsonValue>& Value : *Entries)
		{
			const TSharedPtr<FJsonObject> Entry = Value->AsObject();
			FString Name;
			if (Entry.IsValid() && Entry->TryGetStringField(TEXT("name"), Name))
			{
				Names.Add(Name);
			}
		}
	}
	return Names;
}

void FFuryAnimSet::LoadManifest(const FString& ManifestFile)
{
	FString Text;
	if (ManifestFile.IsEmpty() || !FFileHelper::LoadFileToString(Text, *ManifestFile))
	{
		return;
	}
	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogFury, Warning, TEXT("Animation manifest %s is not valid JSON"), *ManifestFile);
		return;
	}
	const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
	if (!Root->TryGetArrayField(TEXT("clips"), Entries))
	{
		return;
	}
	for (const TSharedPtr<FJsonValue>& Value : *Entries)
	{
		const TSharedPtr<FJsonObject> Entry = Value->AsObject();
		if (!Entry.IsValid())
		{
			continue;
		}
		const int32* Index = ClipIndex.Find(FName(*Entry->GetStringField(TEXT("name"))));
		if (!Index)
		{
			continue;
		}
		FFuryClip& Clip = Clips[*Index];
		Entry->TryGetBoolField(TEXT("loop"), Clip.bLoop);
		double Speed = 0.0;
		if (Entry->TryGetNumberField(TEXT("speed"), Speed))
		{
			Clip.Speed = static_cast<float>(Speed) * 100.f;   // metres per second -> cm per second
		}
		FString Ball;
		if (Entry->TryGetStringField(TEXT("ball"), Ball))
		{
			Clip.Grip = Ball == TEXT("hand") ? EFuryGrip::Hand : Ball == TEXT("tuck") ? EFuryGrip::Tuck : EFuryGrip::None;
		}
		const TSharedPtr<FJsonObject>* Events = nullptr;
		if (Entry->TryGetObjectField(TEXT("events"), Events) && Events->IsValid())
		{
			for (const auto& Pair : (*Events)->Values)
			{
				double Frame = 0.0;
				if (Pair.Value.IsValid() && Pair.Value->TryGetNumber(Frame))
				{
					Clip.Events.Add(FName(*Pair.Key), static_cast<float>(Frame) / BakeRate);
				}
			}
		}
	}
}

const FFuryClip* FFuryAnimSet::Find(FName Name) const
{
	const int32* Index = ClipIndex.Find(Name);
	return Index ? &Clips[*Index] : nullptr;
}

const FFuryClip* FFuryAnimSet::FindFirst(std::initializer_list<const TCHAR*> Names) const
{
	for (const TCHAR* Name : Names)
	{
		if (const FFuryClip* Clip = Find(FName(Name)))
		{
			return Clip;
		}
	}
	return nullptr;
}

int32 FFuryAnimSet::Bone(FName Name) const
{
	return BoneNames.IndexOfByKey(Name);
}
