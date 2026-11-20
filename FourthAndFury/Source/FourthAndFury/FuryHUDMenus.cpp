#include "FuryHUD.h"

#include "FuryDirector.h"
#include "FuryHUDStyle.h"
#include "FuryInput.h"
#include "FuryTeams.h"

// Title, lobby, team select, final score and the pause menu.

using namespace FuryUI;

void AFuryHUD::DrawTitle(AFuryDirector* Director)
{
	const float T = Director->ScreenTime;
	ScreenShade(Fade(Ink, 0.55f), Fade(Ink, 0.82f));

	// The logo punches in, then breathes.
	const float In = Ease(T / 0.6f);
	const float Scale = Director->Options.Get(EFuryOption::ReducedMotion) ? 1.f : FMath::Lerp(1.5f, 1.f, In) * (1.f + 0.012f * FMath::Sin(T * 2.1f));
	const float W = 1240.f * Scale, H = 620.f * Scale;
	if (UTexture* Logo = Director->UiTexture(TEXT("T_Title")))
	{
		Image(Logo, 960.f - W * 0.5f, 400.f - H * 0.5f, W, H, FLinearColor(1.f, 1.f, 1.f, In));
	}
	else
	{
		TextOutline(TEXT("4TH & FURY"), 960.f, 260.f, EFuryFace::BlackItalic, 220.f, Gold, Ink, 8.f, EFuryAlign::Center);
	}
	Text(TEXT("FOUR DOWNS FOR 30 YARDS   /   THREE SECONDS AFTER THE WHISTLE"), 960.f, 688.f, EFuryFace::Bold, 31.f, Fade(White, In), EFuryAlign::Center, 140);

	const int32 Pads = FFuryInput::Get().NumConnectedGamepads();
	for (int32 i = 0; i < 2; ++i)
	{
		const float X = 342.f + i * 629.f;
		Panel(X, 768.f, 606.f, 132.f, i == 0 ? Blaze : Gold, 0.93f);
		Glyph(INDEX_NONE, i == 0 ? FuryUI::A : FuryUI::X, X + 38.f, 802.f, 54.f);
		Text(i == 0 ? TEXT("SET UP MATCH") : TEXT("QUICK SOLO"), X + 116.f, 778.f, EFuryFace::BlackItalic, 52.f, White);
		Text(i == 0 ? TEXT("G / K   •   1–8 players, choose teams") : TEXT("F / J   •   Rookie, one-minute quarters"),
			X + 118.f, 848.f, EFuryFace::SemiBold, 26.f, Dim);
	}
	if (FPlatformProperties::SupportsQuit())
	{
		Prompts(INDEX_NONE, {{ FuryUI::Y, TEXT("SETTINGS  (T / I)") }, { FuryUI::B, TEXT("QUIT GAME  (H / L)") }}, 960.f, 933.f, 30.f);
	}
	else { Prompts(INDEX_NONE, {{ FuryUI::Y, TEXT("SETTINGS  (T / I)") }}, 960.f, 933.f, 30.f); }
	const FString Devices = Pads > 0 ? FString::Printf(TEXT("%d CONTROLLER%s   /   SHARED KEYBOARD"), Pads, Pads == 1 ? TEXT("") : TEXT("S")) : TEXT("KEYBOARD READY   /   CONNECT CONTROLLERS TO ADD PLAYERS");
	Text(Devices, 960.f, 994.f, EFuryFace::SemiBold, 23.f, Dim, EFuryAlign::Center, 100);
}

void AFuryHUD::DrawLobby(AFuryDirector* Director)
{
	const float T = Director->ScreenTime;
	ScreenShade(Fade(Ink, 0.7f), Fade(Ink, 0.88f));
	const float In = Ease(T / 0.35f);
	TextShadow(TEXT("PICK A SIDE"), 960.f, 46.f - 30.f * (1.f - In), EFuryFace::BlackItalic, 96.f, White, EFuryAlign::Center);
	Text(TEXT("MOVE LEFT FOR HOME, RIGHT FOR AWAY  -  A SIDE WITH NOBODY ON IT IS PLAYED BY THE COMPUTER"), 960.f, 152.f, EFuryFace::SemiBold, 24.f, Dim, EFuryAlign::Center, 120);

	const TArray<FFuryTeam>& League = Fury::Teams();
	const float ColumnY = 210.f, ColumnH = 640.f;
	const float ColumnX[3] = { 70.f, 720.f, 1310.f };
	const float ColumnW[3] = { 540.f, 480.f, 540.f };
	const TCHAR* Titles[3] = { TEXT("HOME"), TEXT("WAITING"), TEXT("AWAY") };

	for (int32 Column = 0; Column < 3; ++Column)
	{
		const int32 Side = Column == 0 ? 0 : Column == 2 ? 1 : INDEX_NONE;
		const FLinearColor Accent = Side == INDEX_NONE ? Dim : League[Director->TeamPick[Side]].Primary;
		const float X = ColumnX[Column], W = ColumnW[Column];
		const bool bCompact = Side == INDEX_NONE && Director->NumOnSide(INDEX_NONE) > 4;
		const float RowH = bCompact ? 68.f : 138.f;
		Panel(X, ColumnY, W, ColumnH, Accent, Side == INDEX_NONE ? 0.5f : 0.84f);
		Text(Titles[Column], X + W * 0.5f, ColumnY + 14.f, EFuryFace::BlackItalic, 52.f, Side == INDEX_NONE ? Dim : White, EFuryAlign::Center);

		int32 Row = 0;
		for (int32 i = 0; i < Fury::MaxSeats; ++i)
		{
			const FFuryLobbySeat& Seat = Director->Seats[i];
			if (!Seat.bJoined || Seat.Side != Side)
			{
				continue;
			}
			const float Y = ColumnY + 86.f + Row * RowH;
			++Row;
			const FLinearColor Color = AFuryDirector::SeatColor(i);
			Rect(X + 18.f, Y, W - 36.f, RowH - 14.f, Fade(Color, Seat.bReady ? 0.3f : 0.14f));
			Rect(X + 18.f, Y, 8.f, RowH - 14.f, Color);
			SeatChip(i, X + 44.f, Y + (bCompact ? 6.f : 18.f), bCompact ? 40.f : 62.f, Seat.bBot);
			const FFuryPad* Pad = Director->SeatPad(i);
			const FString Device = Seat.bBot ? FString(TEXT("COMPUTER PLAYER")) : (Pad ? Pad->Label : FString(TEXT("CONTROLLER")));
			Text(Device, X + (bCompact ? 140.f : 168.f), Y + (bCompact ? 10.f : 20.f), EFuryFace::Bold, 30.f, White, EFuryAlign::Left, 60);
			if (bCompact) { continue; }
			if (Side == INDEX_NONE)
			{
				Text(TEXT("<  HOME      AWAY  >"), X + 168.f, Y + 64.f, EFuryFace::SemiBold, 26.f, Fade(Gold, 0.6f + 0.4f * FMath::Sin(T * 5.f)), EFuryAlign::Left, 80);
			}
			else if (Seat.bReady)
			{
				Text(TEXT("READY"), X + 168.f, Y + 60.f, EFuryFace::BlackItalic, 38.f, Good);
			}
			else
			{
				Glyph(i, FuryUI::A, X + 168.f, Y + 66.f, 34.f);
				Text(TEXT("READY UP"), X + 214.f, Y + 68.f, EFuryFace::SemiBold, 28.f, Dim, EFuryAlign::Left, 80);
			}
		}
		if (Side != INDEX_NONE)
		{
			// Open places, or a note that the computer has this side.
			for (; Row < Fury::MaxSeatsPerTeam; ++Row)
			{
				const float Y = ColumnY + 86.f + Row * RowH;
				Frame(X + 18.f, Y, W - 36.f, RowH - 14.f, 2.f, Fade(White, 0.07f));
				const bool bEmptySide = Director->NumOnSide(Side) == 0;
				Text(bEmptySide && Row == 0 ? TEXT("COMPUTER") : TEXT("OPEN"), X + W * 0.5f, Y + 36.f, EFuryFace::BoldItalic, 40.f, Fade(Dim, bEmptySide && Row == 0 ? 0.8f : 0.3f), EFuryAlign::Center, 120);
			}
		}
		else if (Row == 0 && Director->NumJoined() == Fury::MaxSeats)
		{
			Text(TEXT("ALL SEATS FILLED"), X + W * 0.5f, ColumnY + 260.f, EFuryFace::BoldItalic, 40.f, Dim, EFuryAlign::Center);
		}
		else if (Row == 0)
		{
			Text(TEXT("PRESS"), X + W * 0.5f - 60.f, ColumnY + 250.f, EFuryFace::BoldItalic, 40.f, Fade(White, 0.5f + 0.3f * FMath::Sin(T * 4.f)), EFuryAlign::Right);
			Glyph(INDEX_NONE, FuryUI::A, X + W * 0.5f - 44.f, ColumnY + 252.f, 44.f);
			Text(TEXT("TO JOIN"), X + W * 0.5f + 14.f, ColumnY + 250.f, EFuryFace::BoldItalic, 40.f, Fade(White, 0.5f + 0.3f * FMath::Sin(T * 4.f)));
			Text(TEXT("KEYBOARD: G OR K"), X + W * 0.5f, ColumnY + 314.f, EFuryFace::SemiBold, 24.f, Fade(Dim, 0.8f), EFuryAlign::Center, 120);
		}
	}

	if (Director->StartCountdown >= 0.f)
	{
		const float Pulse = 0.7f + 0.3f * FMath::Sin(T * 12.f);
		Slant(560.f, 884.f, 800.f, 92.f, 28.f, Fade(Good, 0.3f));
		TextShadow(TEXT("EVERYBODY'S IN  -  HERE WE GO"), 960.f, 898.f, EFuryFace::BlackItalic, 56.f, Fade(White, Pulse), EFuryAlign::Center);
	}
	else
	{
		Prompts(Director->Picker(0), { { FuryUI::A, TEXT("JOIN / READY") }, { FuryUI::B, TEXT("BACK OUT") }, { FuryUI::Stick, TEXT("CHOOSE SIDE") } }, 960.f, 906.f, 34.f);
	}
	const int32 Pads = FFuryInput::Get().NumConnectedGamepads();
	Text(FString::Printf(TEXT("%d CONTROLLER%s CONNECTED  -  %d OF 8 SEATS TAKEN"), Pads, Pads == 1 ? TEXT("") : TEXT("S"), Director->NumJoined()),
		960.f, 1000.f, EFuryFace::SemiBold, 24.f, Fade(Dim, 0.9f), EFuryAlign::Center, 160);
}

void AFuryHUD::DrawTeamCard(AFuryDirector* Director, int32 Side, float X, float Y, float W)
{
	const FFuryTeam& Team = Fury::Teams()[Director->TeamPick[Side]];
	const float T = Director->ScreenTime;
	const float H = 700.f;
	const bool bLocked = Director->bTeamLocked[Side];
	const int32 Seat = Director->Picker(Side);
	const bool bWaiting = Side == 1 && Seat == Director->Picker(0) && !Director->bTeamLocked[0];
	const bool bActive = !bWaiting && !bLocked && Director->OptionRow[Side] == 0;

	Panel(X, Y, W, H, Team.Primary, 0.88f);
	// A band of the team's colours across the top.
	GradientH(X, Y + 5.f, W, 112.f, Fade(Team.Primary, 0.95f), Fade(Team.Primary, 0.35f));
	Rect(X, Y + 117.f, W, 6.f, Team.Secondary);
	Text(Side == 0 ? TEXT("HOME") : TEXT("AWAY"), X + 26.f, Y + 18.f, EFuryFace::Bold, 28.f, InkOn(Team.Primary), EFuryAlign::Left, 300);
	if (Seat != INDEX_NONE && Director->NumOnSide(Side) > 0)
	{
		SeatChip(Seat, X + W - 130.f, Y + 22.f, 40.f);
	}
	else
	{
		SeatChip(0, X + W - 150.f, Y + 22.f, 40.f, true);
	}
	Text(Team.City.ToUpper(), X + 26.f, Y + 56.f, EFuryFace::SemiBold, 40.f, InkOn(Team.Primary), EFuryAlign::Left, 160);

	if (UTexture* Logo = Director->TeamLogo(Director->TeamPick[Side]))
	{
		Image(Logo, X + W * 0.5f - 130.f, Y + 136.f, 260.f, 260.f);
	}
	const float NameSize = Team.Name.Len() > 9 ? 70.f : 86.f;
	TextShadow(Team.Name.ToUpper(), X + W * 0.5f, Y + 392.f, EFuryFace::BlackItalic, NameSize, White, EFuryAlign::Center);

	// Ratings.
	const TCHAR* Labels[4] = { TEXT("SPEED"), TEXT("POWER"), TEXT("PASSING"), TEXT("DEFENSE") };
	const int32 Values[4] = { Team.Speed, Team.Power, Team.Passing, Team.Defense };
	for (int32 i = 0; i < 4; ++i)
	{
		const float RowY = Y + 492.f + i * 38.f;
		Text(Labels[i], X + 40.f, RowY, EFuryFace::Bold, 24.f, Dim, EFuryAlign::Left, 140);
		for (int32 k = 0; k < 5; ++k)
		{
			Slant(X + 200.f + k * 60.f, RowY + 4.f, 52.f, 20.f, 8.f, k < Values[i] ? (Team.Primary.GetLuminance() < 0.04f ? Team.Secondary : Team.Primary) : Fade(White, 0.09f));
		}
	}
	Text(Team.Motto, X + W * 0.5f, Y + 652.f, EFuryFace::BoldItalic, 24.f, Fade(White, 0.75f), EFuryAlign::Center, 40);

	if (bLocked)
	{
		Slant(X + 30.f, Y + 250.f, W - 60.f, 84.f, 26.f, Fade(Good, 0.92f));
		Text(TEXT("LOCKED IN"), X + W * 0.5f + 12.f, Y + 258.f, EFuryFace::BlackItalic, 62.f, Ink, EFuryAlign::Center);
	}
	else if (bActive)
	{
		// Arrows nudge in and out to say "left and right change this".
		const float Nudge = 8.f * FMath::Sin(T * 6.f);
		Triangle(FVector2D(X - 22.f - Nudge, Y + 266.f), FVector2D(X + 6.f - Nudge, Y + 236.f), FVector2D(X + 6.f - Nudge, Y + 296.f), Gold);
		Triangle(FVector2D(X + W + 22.f + Nudge, Y + 266.f), FVector2D(X + W - 6.f + Nudge, Y + 236.f), FVector2D(X + W - 6.f + Nudge, Y + 296.f), Gold);
	}
}

void AFuryHUD::DrawTeams(AFuryDirector* Director)
{
	const float T = Director->ScreenTime;
	GradientV(0.f, 0.f, 1920.f, 300.f, Fade(Ink, 0.85f), Fade(Ink, 0.f));
	GradientV(0.f, 700.f, 1920.f, 380.f, Fade(Ink, 0.f), Fade(Ink, 0.9f));
	TextShadow(TEXT("CHOOSE YOUR TEAMS"), 960.f, 30.f, EFuryFace::BlackItalic, 84.f, White, EFuryAlign::Center);

	DrawTeamCard(Director, 0, 60.f, 150.f, 560.f);
	DrawTeamCard(Director, 1, 1300.f, 150.f, 560.f);
	TextOutline(TEXT("VS"), 960.f, 150.f, EFuryFace::BlackItalic, 110.f, Gold, Ink, 6.f, EFuryAlign::Center);

	// Match options, owned by whoever picks first.
	const int32 Owner = Director->Picker(0);
	const int32 Row = Director->OptionRow[0];
	const bool bEditing = Owner != INDEX_NONE && !Director->bTeamLocked[0];
	const float PX = 690.f, PY = 800.f, PW = 540.f;
	Panel(PX, PY, PW, 150.f, Gold, 0.86f);
	const FString Quarter = FString::Printf(TEXT("%d:%02d"), FMath::RoundToInt32(Director->QuarterSeconds()) / 60, FMath::RoundToInt32(Director->QuarterSeconds()) % 60);
	const TCHAR* Names[2] = { TEXT("QUARTER LENGTH"), TEXT("COMPUTER SKILL") };
	const FString Values[2] = { Quarter, AFuryDirector::SkillName(Director->SkillChoice) };
	for (int32 i = 0; i < 2; ++i)
	{
		const float Y = PY + 22.f + i * 60.f;
		const bool bHot = bEditing && Row == i + 1;
		if (bHot)
		{
			Rect(PX + 10.f, Y - 6.f, PW - 20.f, 54.f, Fade(Gold, 0.18f + 0.08f * FMath::Sin(T * 6.f)));
		}
		Text(Names[i], PX + 30.f, Y + 4.f, EFuryFace::Bold, 28.f, bHot ? White : Dim, EFuryAlign::Left, 120);
		Text(FString::Printf(TEXT("<  %s  >"), *Values[i]), PX + PW - 30.f, Y - 2.f, EFuryFace::BlackItalic, 38.f, bHot ? Gold : White, EFuryAlign::Right);
	}

	if (Director->StartCountdown >= 0.f)
	{
		TextOutline(TEXT("KICKOFF!"), 960.f, 978.f, EFuryFace::BlackItalic, 70.f, White, Ink, 5.f, EFuryAlign::Center);
	}
	else
	{
		const int32 ActiveSide = Director->bTeamLocked[0] ? 1 : 0;
		Prompts(Director->Picker(ActiveSide), { { FuryUI::Stick, TEXT("CHANGE") }, { FuryUI::A, TEXT("LOCK IN") }, { FuryUI::B, TEXT("BACK") } }, 960.f, 990.f, 32.f);
	}
}

void AFuryHUD::DrawFinal(AFuryDirector* Director)
{
	if (Director->bViewingFilm) { DrawFilm(Director); return; }
	const FFurySim& Sim = Director->Sim;
	const float T = Director->ScreenTime;
	ScreenShade(Fade(Ink, 0.78f), Fade(Ink, 0.92f));
	const int32 Winner = Sim.Winner();
	const FString Headline = Winner == INDEX_NONE ? FString(TEXT("TIE GAME")) : Sim.TeamInfo(Winner).Name.ToUpper() + TEXT(" WIN!");
	const FLinearColor Accent = Winner == INDEX_NONE ? Gold : Sim.TeamInfo(Winner).Primary;
	const float In = Ease(T / 0.4f);
	Slant(260.f - 800.f * (1.f - In), 40.f, 1400.f, 150.f, 46.f, Fade(Accent, 0.9f));
	TextShadow(Headline, 960.f, 48.f, EFuryFace::BlackItalic, 124.f, InkOn(Accent), EFuryAlign::Center);

	// Scores with emblems.
	for (int32 Team = 0; Team < 2; ++Team)
	{
		const FFuryTeam& Info = Sim.TeamInfo(Team);
		const float X = Team == 0 ? 220.f : 1100.f;
		Panel(X, 230.f, 600.f, 230.f, Info.Primary, 0.88f);
		if (UTexture* Logo = Director->TeamLogo(Sim.Teams[Team].League))
		{
			Image(Logo, X + 22.f, 256.f, 180.f, 180.f);
		}
		Text(Info.City.ToUpper(), X + 220.f, 248.f, EFuryFace::SemiBold, 30.f, Dim, EFuryAlign::Left, 160);
		Text(Info.Name.ToUpper(), X + 220.f, 285.f, EFuryFace::BlackItalic, 50.f, White);
		TextShadow(FString::FromInt(Sim.Teams[Team].Score), X + 572.f, 336.f, EFuryFace::BlackItalic, 104.f, Team == Winner ? Gold : White, EFuryAlign::Right);
	}

	// Box score.
	const float BX = 220.f, BY = 490.f, BW = 1480.f;
	Panel(BX, BY, BW, 400.f, Gold, 0.86f);
	const TCHAR* Columns[] = { TEXT("1"), TEXT("2"), TEXT("3"), TEXT("4"), TEXT("OT"), TEXT("PASS YDS"), TEXT("RUSH YDS"), TEXT("COMP"), TEXT("SACKS"), TEXT("PICKS"), TEXT("BIG HITS") };
	const float ColX[] = { 420.f, 480.f, 540.f, 600.f, 668.f, 800.f, 950.f, 1090.f, 1210.f, 1320.f, 1440.f };
	for (int32 c = 0; c < 11; ++c)
	{
		Text(Columns[c], BX + ColX[c], BY + 26.f, EFuryFace::Bold, 22.f, Dim, EFuryAlign::Right, 100);
	}
	for (int32 Team = 0; Team < 2; ++Team)
	{
		const FFuryTeamState& St = Sim.Teams[Team];
		const float Y = BY + 64.f + Team * 62.f;
		Rect(BX + 20.f, Y - 6.f, 10.f, 52.f, Sim.TeamInfo(Team).Primary);
		Text(Sim.TeamInfo(Team).Name.ToUpper(), BX + 46.f, Y, EFuryFace::BoldItalic, 36.f, White);
		const FString Cells[] = { FString::FromInt(St.ScoreByQuarter[0]), FString::FromInt(St.ScoreByQuarter[1]), FString::FromInt(St.ScoreByQuarter[2]), FString::FromInt(St.ScoreByQuarter[3]),
			Sim.bOvertime ? FString::FromInt(St.ScoreByQuarter[4]) : FString(TEXT("-")), FString::FromInt(St.PassYards), FString::FromInt(St.RushYards),
			FString::Printf(TEXT("%d/%d"), St.Completions, St.Attempts), FString::FromInt(St.Sacks), FString::FromInt(St.Picks), FString::FromInt(St.BigHits) };
		for (int32 c = 0; c < 11; ++c)
		{
			Text(Cells[c], BX + ColX[c], Y + 2.f, EFuryFace::Bold, 32.f, White, EFuryAlign::Right);
		}
	}

	// Who did what at the table.
	Text(TEXT("AT THE CONTROLS"), BX + 46.f, BY + 210.f, EFuryFace::Bold, 22.f, Dim, EFuryAlign::Left, 240);
	int32 Shown = 0;
	for (int32 i = 0; i < Fury::MaxSeats; ++i)
	{
		const FFurySeat& Seat = Sim.Seats[i];
		if (!Seat.bActive)
		{
			continue;
		}
		const float X = BX + 46.f + (Shown % 4) * 360.f, Y = BY + 246.f + (Shown / 4) * 70.f;
		++Shown;
		const float ChipW = SeatChip(i, X, Y, 44.f, Director->Seats[i].bBot);
		Text(FString::Printf(TEXT("%d TD   %d TKL   %d INT"), Seat.Touchdowns, Seat.Tackles, Seat.Picks), X + ChipW + 12.f, Y + 6.f, EFuryFace::SemiBold, 26.f, White, EFuryAlign::Left, 40);
	}
	if (Shown == 0)
	{
		Text(TEXT("COMPUTER VS COMPUTER"), BX + 46.f, BY + 250.f, EFuryFace::BoldItalic, 34.f, Fade(White, 0.6f));
	}

	const int32 Leader = Director->Film.BestTeam != INDEX_NONE ? Director->Film.BestTeam : (Sim.Teams[0].LongestTD >= Sim.Teams[1].LongestTD ? 0 : 1);
	const FFuryTeamState& Long = Sim.Teams[Leader];
	if (Sim.TeamInfo(Leader).Roster.IsValidIndex(Long.LongestScorer))
	{
		const FFuryRosterEntry& Player = Sim.TeamInfo(Leader).Roster[Long.LongestScorer];
		const FString Play = FString::Printf(TEXT("LONGEST TOUCHDOWN    /    %d YD %s    /    %s  #%d  %s"), Long.LongestTD, *Long.LongestType, *Sim.TeamInfo(Leader).Abbr, Player.Number, *Player.Name.ToUpper());
		Text(Play, 960.f, 896.f, EFuryFace::Bold, 29.f, Gold, EFuryAlign::Center);
	}
	if (T > 1.f)
	{
		if (Director->SelectedFilm().Ready())
		{
			Prompts(Director->Picker(0), { { FuryUI::A, TEXT("REMATCH") }, { FuryUI::B, TEXT("CHANGE TEAMS") }, { FuryUI::Y, Director->Film.LongestTouchdown.Ready() ? TEXT("REPLAY TOUCHDOWN") : TEXT("PLAY FILM") } }, 960.f, 946.f, 38.f);
		}
		else { Prompts(Director->Picker(0), { { FuryUI::A, TEXT("REMATCH") }, { FuryUI::B, TEXT("CHANGE TEAMS") } }, 960.f, 946.f, 38.f); }
		if (FPlatformProperties::SupportsQuit()) { Prompts(Director->Picker(0), {{FuryUI::X, TEXT("QUIT GAME")}}, 960.f, 1013.f, 26.f); }
	}
}

void AFuryHUD::DrawPause(AFuryDirector* Director)
{
	ScreenShade(Fade(Ink, 0.72f));
	if (Director->bViewingFilm) { DrawFilm(Director); return; }
	if (Director->bFieldGuide) { DrawFieldGuide(Director); return; }
	Panel(610.f, 268.f, 700.f, 602.f, Blaze, 0.94f);
	TextShadow(TEXT("TIME OUT"), 960.f, 304.f, EFuryFace::BlackItalic, 96.f, White, EFuryAlign::Center);
	if (Director->PauseSeat != INDEX_NONE)
	{
		SeatChip(Director->PauseSeat, 862.f, 414.f, 40.f);
		Text(TEXT("CALLED IT"), 944.f, 418.f, EFuryFace::SemiBold, 28.f, Dim, EFuryAlign::Left, 120);
	}
	if (Director->bConfirmPauseAction)
	{
		const bool bRestart = Director->PauseCursor == 2;
		Text(bRestart ? TEXT("RESTART THIS MATCH?") : TEXT("LEAVE THIS MATCH?"), 960.f, 506.f, EFuryFace::BlackItalic, 52.f, Gold, EFuryAlign::Center);
		Text(TEXT("The current score will be cleared."), 960.f, 580.f, EFuryFace::SemiBold, 32.f, White, EFuryAlign::Center);
		Prompts(Director->PauseSeat, { { FuryUI::A, bRestart ? TEXT("RESTART") : TEXT("LEAVE") }, { FuryUI::B, TEXT("CANCEL") } }, 960.f, 672.f, 32.f);
		return;
	}
	const TCHAR* Items[] = { TEXT("BACK TO THE GAME"), TEXT("SETTINGS"), TEXT("RESTART MATCH"), TEXT("RETURN TO TITLE"), TEXT("QUIT GAME") };
	for (int32 i = 0; i < UE_ARRAY_COUNT(Items) - (FPlatformProperties::SupportsQuit() ? 0 : 1); ++i)
	{
		const float Y = 481.f + i * 74.f;
		const bool bHot = Director->PauseCursor == i;
		if (bHot)
		{
			Slant(660.f, Y - 6.f, 600.f, 66.f, 20.f, Blaze);
		}
		Text(Items[i], 960.f + (bHot ? 10.f : 0.f), Y, EFuryFace::BlackItalic, 46.f, bHot ? Ink : Fade(White, 0.7f), EFuryAlign::Center);
	}
	if (Director->Film.Last.Ready())
	{
		Prompts(Director->PauseSeat, { { FuryUI::A, TEXT("CHOOSE") }, { FuryUI::X, TEXT("FIELD GUIDE") }, { FuryUI::Y, TEXT("PLAY FILM") }, { FuryUI::B, TEXT("RESUME") } }, 960.f, 894.f, 30.f);
	}
	else { Prompts(Director->PauseSeat, { { FuryUI::A, TEXT("CHOOSE") }, { FuryUI::X, TEXT("FIELD GUIDE") }, { FuryUI::B, TEXT("RESUME") } }, 960.f, 894.f, 30.f); }
}
