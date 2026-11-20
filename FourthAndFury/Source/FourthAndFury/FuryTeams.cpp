#include "FuryTeams.h"

namespace
{
	struct FNames { const TCHAR* Offense[7]; const TCHAR* Defense[7]; const TCHAR* Kicker; };

	FFuryTeam Make(const TCHAR* Id, const TCHAR* City, const TCHAR* Name, const TCHAR* Abbr,
		const TCHAR* Primary, const TCHAR* Secondary, const TCHAR* Accent, const TCHAR* Helmet,
		int32 Speed, int32 Power, int32 Passing, int32 Defense, const TCHAR* Motto, const FNames& Names, int32 Seed)
	{
		FFuryTeam Team;
		Team.Id = Id; Team.City = City; Team.Name = Name; Team.Abbr = Abbr;
		Team.Primary = Fury::Hex(Primary); Team.Secondary = Fury::Hex(Secondary);
		Team.Accent = Fury::Hex(Accent); Team.Helmet = Fury::Hex(Helmet);
		Team.Speed = Speed; Team.Power = Power; Team.Passing = Passing; Team.Defense = Defense;
		Team.Motto = Motto;

		static const EFuryPos OffensePos[7] = { EFuryPos::QB, EFuryPos::OL, EFuryPos::OL, EFuryPos::OL, EFuryPos::WR, EFuryPos::WR, EFuryPos::RB };
		static const EFuryPos DefensePos[7] = { EFuryPos::DL, EFuryPos::DL, EFuryPos::DL, EFuryPos::LB, EFuryPos::CB, EFuryPos::CB, EFuryPos::S };
		// Numbers by position group, the way real rosters hand them out.
		static const int32 OffenseBase[7] = { 7, 52, 61, 74, 80, 11, 21 };
		static const int32 DefenseBase[7] = { 90, 95, 99, 50, 20, 30, 40 };

		FRandomStream Random(Seed);
		TSet<int32> Used;
		auto Number = [&Random, &Used](int32 Base)
		{
			int32 N = Base + Random.RandRange(0, 8);
			if (Base >= 90) { N = 90 + (N - 90) % 10; }
			while (Used.Contains(N))
			{
				N = Base >= 90 ? 90 + (N - 89) % 10 : N % 99 + 1;
			}
			Used.Add(N);
			return N;
		};
		auto Add = [&](const TCHAR* PlayerName, EFuryPos Pos, int32 Base)
		{
			FFuryRosterEntry Entry;
			Entry.Name = PlayerName;
			Entry.Pos = Pos;
			Entry.Number = Number(Base);
			Entry.SkinTone = Random.RandRange(0, Fury::SkinTones().Num() - 1);
			Entry.bVisor = Pos != EFuryPos::OL && Pos != EFuryPos::DL && Pos != EFuryPos::K && Random.FRand() < 0.45f;
			Team.Roster.Add(Entry);
		};
		for (int32 i = 0; i < 7; ++i) { Add(Names.Offense[i], OffensePos[i], OffenseBase[i]); }
		for (int32 i = 0; i < 7; ++i) { Add(Names.Defense[i], DefensePos[i], DefenseBase[i]); }
		Add(Names.Kicker, EFuryPos::K, 2);
		return Team;
	}
}

FLinearColor Fury::Hex(const TCHAR* Code)
{
	return FLinearColor(FColor::FromHex(Code));
}

const TArray<FLinearColor>& Fury::SkinTones()
{
	static const TArray<FLinearColor> Tones = {
		Hex(TEXT("#F1C9A5")), Hex(TEXT("#E0AC84")), Hex(TEXT("#C68958")), Hex(TEXT("#A0683F")), Hex(TEXT("#7A4A2B")), Hex(TEXT("#55321C")),
	};
	return Tones;
}

const TArray<FFuryTeam>& Fury::Teams()
{
	static const TArray<FFuryTeam> League = {
		Make(TEXT("sasquatch"), TEXT("Portland"), TEXT("Sasquatch"), TEXT("POR"), TEXT("#1F6B3A"), TEXT("#EFE6CC"), TEXT("#6B4423"), TEXT("#1F6B3A"),
			2, 5, 3, 4, TEXT("Big. Hairy. Impossible to tackle."),
			{ { TEXT("Hollis"), TEXT("Brannigan"), TEXT("Oyelaran"), TEXT("Tuck"), TEXT("Maddox"), TEXT("Sorrel"), TEXT("Bigfoot Dunn") },
			  { TEXT("Krull"), TEXT("Vandermeer"), TEXT("Okafor"), TEXT("Stonebridge"), TEXT("Pines"), TEXT("Ashdown"), TEXT("Larkspur") }, TEXT("Twiggs") }, 11),
		Make(TEXT("volcanoes"), TEXT("Honolulu"), TEXT("Volcanoes"), TEXT("HNL"), TEXT("#1A1A1E"), TEXT("#FF5A1F"), TEXT("#FFC21A"), TEXT("#1A1A1E"),
			3, 3, 5, 2, TEXT("Every drive ends in an eruption."),
			{ { TEXT("Kealoha"), TEXT("Tavita"), TEXT("Makoa"), TEXT("Brewer"), TEXT("Nakamura"), TEXT("Fontaine"), TEXT("Palakiko") },
			  { TEXT("Lolohea"), TEXT("Ashby"), TEXT("Kanoa"), TEXT("Ferreira"), TEXT("Soares"), TEXT("Wyndham"), TEXT("Ikaika") }, TEXT("Pua") }, 23),
		Make(TEXT("icebreakers"), TEXT("Anchorage"), TEXT("Icebreakers"), TEXT("ANC"), TEXT("#0F3470"), TEXT("#8FE3FF"), TEXT("#FFFFFF"), TEXT("#F4F8FB"),
			3, 4, 2, 5, TEXT("Nothing gets through the ice."),
			{ { TEXT("Lindqvist"), TEXT("Baranov"), TEXT("Tuttle"), TEXT("Halvorsen"), TEXT("Frost"), TEXT("Okpik"), TEXT("Mercer") },
			  { TEXT("Kowalczyk"), TEXT("Bjornson"), TEXT("Steele"), TEXT("Northrup"), TEXT("Winters"), TEXT("Aklaq"), TEXT("Glacier Reed") }, TEXT("Sorenson") }, 37),
		Make(TEXT("hellhounds"), TEXT("Memphis"), TEXT("Hellhounds"), TEXT("MEM"), TEXT("#B01228"), TEXT("#26262B"), TEXT("#FF8A1F"), TEXT("#26262B"),
			4, 4, 3, 3, TEXT("Off the leash since kickoff."),
			{ { TEXT("Beaumont"), TEXT("Calloway"), TEXT("Durand"), TEXT("Pickett"), TEXT("Delacroix"), TEXT("Rhodes"), TEXT("Tallchief") },
			  { TEXT("Graves"), TEXT("Montrose"), TEXT("Lockhart"), TEXT("Cerberus Hale"), TEXT("Ember"), TEXT("Voss"), TEXT("Kincaid") }, TEXT("Dupree") }, 41),
		Make(TEXT("twisters"), TEXT("Omaha"), TEXT("Twisters"), TEXT("OMA"), TEXT("#F2B90F"), TEXT("#2E3440"), TEXT("#FFFFFF"), TEXT("#2E3440"),
			5, 2, 3, 3, TEXT("You will not see them coming."),
			{ { TEXT("Whitlock"), TEXT("Dombrowski"), TEXT("Haskell"), TEXT("Yoder"), TEXT("Gale"), TEXT("Swift"), TEXT("Cyclone Banks") },
			  { TEXT("Rourke"), TEXT("Tillman"), TEXT("Abernathy"), TEXT("Funnel"), TEXT("Zephyr"), TEXT("Lund"), TEXT("Prairie") }, TEXT("Kessler") }, 59),
		Make(TEXT("amps"), TEXT("Austin"), TEXT("Amps"), TEXT("ATX"), TEXT("#E6007E"), TEXT("#15151A"), TEXT("#19E6FF"), TEXT("#15151A"),
			4, 2, 4, 3, TEXT("Turned all the way up."),
			{ { TEXT("Valentine"), TEXT("Ruiz"), TEXT("McAllister"), TEXT("Boone"), TEXT("Reverb Jones"), TEXT("Castillo"), TEXT("Fuzz") },
			  { TEXT("Riff Lawson"), TEXT("Trevino"), TEXT("Stack"), TEXT("Overdrive"), TEXT("Marquez"), TEXT("Ziegler"), TEXT("Feedback") }, TEXT("Tremolo") }, 67),
		Make(TEXT("scorpions"), TEXT("Tucson"), TEXT("Scorpions"), TEXT("TUC"), TEXT("#12A594"), TEXT("#EBCB8B"), TEXT("#1B1B1F"), TEXT("#EBCB8B"),
			4, 3, 3, 4, TEXT("Quiet in the sand. Then the sting."),
			{ { TEXT("Navarro"), TEXT("Begay"), TEXT("Ortega"), TEXT("Sandoval"), TEXT("Mesa"), TEXT("Quill"), TEXT("Dustin Vega") },
			  { TEXT("Stinger"), TEXT("Yazzie"), TEXT("Calderon"), TEXT("Saguaro"), TEXT("Rios"), TEXT("Tovar"), TEXT("Mirage") }, TEXT("Coronado") }, 73),
		Make(TEXT("gargoyles"), TEXT("Brooklyn"), TEXT("Gargoyles"), TEXT("BKN"), TEXT("#6C3BD1"), TEXT("#9AA1AB"), TEXT("#F2F2F2"), TEXT("#9AA1AB"),
			3, 4, 3, 4, TEXT("Stone cold. Always watching."),
			{ { TEXT("Castellano"), TEXT("Abramowitz"), TEXT("Okonkwo"), TEXT("Rizzo"), TEXT("Spire"), TEXT("Delancey"), TEXT("Granite") },
			  { TEXT("Morello"), TEXT("Flatbush"), TEXT("Wojcik"), TEXT("Gable"), TEXT("Cornice"), TEXT("Ledge"), TEXT("Nightwatch") }, TEXT("Finch") }, 89),
	};
	return League;
}

Fury::FKit Fury::KitFor(const FFuryTeam& Team, bool bHome)
{
	FKit Kit;
	const FLinearColor White(0.93f, 0.93f, 0.93f);
	const FLinearColor Black(0.015f, 0.015f, 0.018f);
	auto Luma = [](const FLinearColor& C) { return 0.2126f * C.R + 0.7152f * C.G + 0.0722f * C.B; };
	const bool bDarkPrimary = Luma(Team.Primary) < 0.03f;

	if (bHome)
	{
		Kit.Jersey = Team.Primary;
		Kit.Trim = Team.Secondary;
		// Numbers must stand off the jersey: light on dark, dark on light.
		Kit.NumberFill = Luma(Team.Primary) > 0.35f ? Black : (Luma(Team.Secondary) > 0.3f ? Team.Secondary : White);
		Kit.NumberEdge = Luma(Kit.NumberFill) > 0.3f ? (bDarkPrimary ? Team.Accent : Black) : White;
		Kit.Pants = Luma(Team.Secondary) > 0.25f ? Team.Secondary : White;
		Kit.PantsStripe = Team.Primary;
	}
	else
	{
		Kit.Jersey = White;
		Kit.Trim = Team.Primary;
		Kit.NumberFill = bDarkPrimary ? Team.Secondary : Team.Primary;
		Kit.NumberEdge = bDarkPrimary ? Black : Team.Secondary;
		if (Luma(Kit.NumberFill) > 0.5f)
		{
			Kit.NumberFill = Black;
			Kit.NumberEdge = Team.Primary;
		}
		Kit.Pants = bDarkPrimary ? Team.Primary : (Luma(Team.Primary) > 0.3f ? Team.Secondary : Team.Primary);
		Kit.PantsStripe = White;
	}
	Kit.Helmet = Team.Helmet;
	Kit.HelmetStripe = Luma(Team.Helmet) > 0.5f ? Team.Primary : (Luma(Team.Secondary) > Luma(Team.Helmet) + 0.05f ? Team.Secondary : Team.Accent);
	Kit.Facemask = Luma(Team.Helmet) > 0.5f ? Team.Primary : FLinearColor(0.7f, 0.7f, 0.72f);
	Kit.Socks = bHome ? Kit.Jersey : Team.Primary;
	Kit.Shoes = bHome ? Black : White;
	Kit.Gloves = bHome ? Team.Accent : Team.Primary;
	return Kit;
}
