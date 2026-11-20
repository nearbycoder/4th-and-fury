#pragma once

#include "CoreMinimal.h"
#include "FuryTypes.h"

/** One athlete on a team sheet. */
struct FFuryRosterEntry
{
	FString Name;
	int32 Number = 0;
	EFuryPos Pos = EFuryPos::WR;
	int32 SkinTone = 0;     // index into Fury::SkinTones
	bool bVisor = false;
};

/**
 * A team in the Fury Football League. Ratings run 1..5.
 * Keep the ids and colours in step with Art/teams.json, which the art scripts read.
 */
struct FFuryTeam
{
	FString Id, City, Name, Abbr;
	FLinearColor Primary, Secondary, Accent, Helmet;
	int32 Speed = 3, Power = 3, Passing = 3, Defense = 3;
	FString Motto;

	// Slots 0..6: QB, C, LG, RG, WR, WR, RB.   Slots 7..13: DE, DT, DE, LB, CB, CB, S.   Slot 14: K.
	TArray<FFuryRosterEntry> Roster;

	FString FullName() const { return City + TEXT(" ") + Name; }
};

namespace Fury
{
	constexpr int32 OffenseSlot0 = 0;
	constexpr int32 DefenseSlot0 = 7;
	constexpr int32 KickerSlot = 14;

	const TArray<FFuryTeam>& Teams();
	const TArray<FLinearColor>& SkinTones();

	/** Parses "#RRGGBB" as an sRGB colour and returns it in linear space. */
	FLinearColor Hex(const TCHAR* Code);

	/** Uniform colours for a team wearing its home (coloured) or away (white) kit. */
	struct FKit
	{
		FLinearColor Jersey, Trim, NumberFill, NumberEdge, Pants, PantsStripe, Helmet, HelmetStripe, Facemask, Socks, Shoes, Gloves;
	};
	FKit KitFor(const FFuryTeam& Team, bool bHome);
}
