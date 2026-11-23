"""Build a test fixture from the hand-researched Southwell 24 Nov 2026 card and
past late-November Southwell renewals (sources: Sporting Life results pages).
Writes rpscrape-shaped files so the real import path is exercised."""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures")


def lbs(sl):
    st, lb = sl.split("-")
    return int(st) * 14 + int(lb)


# (race_id, date, off, name, class, dist, going, ran, [(pos, horse, age, wt, sp, trainer, jockey)])
PAST = [
    ("891048", "2025-11-25", "12:40", "Grace And Dotty Country Clothing Handicap Chase", 5, "2m4f88y", "Good To Soft", 9, [
        ("1", "Bravethewaves", 8, "10-7", "11/2", "O Greenall & J Guerriero", "Toby Wynne"),
        ("2", "Ceolwulf", 9, "11-5", "11/4J", "Fionn McSharry", "S Bowen"),
        ("3", "Onewayortother", 7, "12-0", "8/1", "T Lawes", "K Brogan"),
        ("4", "Rehill Relic", 6, "11-12", "5/1", "S Allwood", "Jack Andrews"),
        ("5", "Valence D'Aumont", 11, "10-11", "11/4J", "J Parkinson & S Smith", "Danny McMenamin"),
        ("6", "Le Beau Gosse", 4, "11-5", "25/1", "O Greenall & J Guerriero", "Craig Nichol"),
        ("PU", "Steady The Ship", 9, "11-10", "25/1", "S Cameron", "Tabitha Worsley"),
        ("PU", "Iddergem", 9, "11-7", "66/1", "Miss C Dyson", "Alice Stevens"),
        ("F", "Jack Doyen", 9, "10-9", "11/1", "B I Case", "J M Quinlan")]),
    ("831311", "2024-11-26", "13:05", "Southwell Golf Club Handicap Chase", 4, "2m4f88y", "Good (Good To Soft In Places)", 10, [
        ("1", "Jasmin De Grugy", None, "11-12", "9/4F", "A J Honeyball", "R P McLernon"),
        ("2", "Knockanore", None, "11-12", "11/2", "R Potter", "Dylan Johnston"),
        ("3", "Onewayortother", None, "11-10", "5/1", "T Lawes", "K Brogan"),
        ("4", "Maninsane", None, "11-8", "12/1", "C E Longsdon", "Lily Pinchin"),
        ("5", "Great Samourai", None, "12-2", "10/1", "C & A Pogson", "C J Todd"),
        ("6", "You Say Nothing", None, "11-0", "33/1", "Christian Williams", "Jack Tudor"),
        ("7", "Duo D'Enfer", None, "12-0", "40/1", "Micky Hammond", "Emma Smith-Chaston"),
        ("PU", "Goldwyn", None, "", "9/1", "M Walford", "Charlie Deutsch"),
        ("PU", "Give Me A Boom", None, "", "17/2", "Dr R Newland", "Luke Scott"),
        ("PU", "Copper Beach", None, "", "13/2", "J Parkinson & S Smith", "Nick Scholfield")]),
    ("771083", "2023-11-28", "12:40", "planetsportbet.com Handicap Chase", 4, "2m4f88y", "Heavy (Soft In Places)", 4, [
        ("1", "Sageburg County", None, "", "16/5", "W Greatrex", "James Bowen"),
        ("2", "Tom Creen", None, "", "6/4F", "S England", "Jonathan England"),
        ("3", "Generous Day", None, "", "9/2", "Henry Oliver", "James Davies"),
        ("UR", "Fazayte", None, "", "11/4", "R Potter", "Jack Hogan")]),
    ("714704", "2022-11-29", "13:00", "Best Odds Guaranteed At Vickers.Bet Handicap Chase", 4, "2m4f88y", "Good (Good To Soft In Places)", 11, [
        ("1", "Gemirande", 6, "11-4", "7/4F", "Miss V Williams", "Charlie Deutsch"),
        ("2", "Our Jet", 6, "11-12", "9/4", "D Skelton", "Harry Skelton"),
        ("3", "Rakhine State", 9, "11-7", "50/1", "D J Jeffreys", "Kielan Woods"),
        ("4", "Coupdebol", 7, "11-4", "11/2", "T R George", "J J Burke")]),
    # distractor: same day, mares' novices' chase - should NOT be picked for the 2m4f handicap chase
    ("714703", "2022-11-29", "12:25", "Join Vickers.Bet Free Bet Club Mares' Novices' Handicap Chase", 4, "2m4f88y", "Good (Good To Soft In Places)", 8, [
        ("1", "Ile De Jersey", None, "", "9/4F", "N J Henderson", "N de Boinville")]),

    ("891049", "2025-11-25", "13:15", "At The Races App Expert Tips Novices' Handicap Chase", 5, "3m60y", "Good To Soft", 7, [
        ("1", "Queens Wish", 6, "11-12", "4/1", "C & A Pogson", "C J Todd"),
        ("2", "Frankie Faulkner", 8, "10-13", "9/2", "Evan Williams", "Isabel Williams"),
        ("3", "Inedit De Mee", 7, "12-0", "5/1", "T Lawes", "K Brogan"),
        ("4", "King Of Cong", 7, "11-12", "7/2", "S England", "Tom Midgley"),
        ("5", "Twp Stori", 7, "11-3", "10/3F", "S Drinkwater", "Benjamin Macey"),
        ("6", "Honneur De Sivola", 8, "10-6", "12/1", "C Hobson", "Lily Pinchin"),
        ("PU", "Luminaries", 8, "11-6", "16/1", "Ewan Whillans", "Sean Quinlan")]),
    ("831310", "2024-11-26", "12:35", "Golf And Gallop Package Mares' Handicap Chase", 5, "3m60y", "Good (Good To Soft In Places)", 6, [
        ("1", "Smurfette", 6, "11-9", "9/4", "T Ellis", "Miss Gina Andrews"),
        ("2", "Northern Reel", 6, "10-8", "6/5F", "O Murphy", "S Bowen"),
        ("3", "Bella Ciao", 7, "10-2", "6/1", "M Keighley", "James Best"),
        ("4", "Just Jess", 8, "10-5", "16/1", "J Parkinson & S Smith", "Alan Doyle"),
        ("5", "Eightytwo Team", 8, "10-3", "7/1", "C Ellam", "Brendan Powell"),
        ("PU", "Nowinittowinit", 8, "12-0", "40/1", "J Bedi", "Aaron Anderson")]),
    ("771084", "2023-11-28", "13:10", "Download The PlanetSportBet App Handicap Chase", 5, "3m60y", "Heavy (Soft In Places)", 6, [
        ("1", "Ali Star Bert", 7, "11-8", "9/2", "S A Harris", "J M Quinlan"),
        ("2", "Sadler's Bay", 6, "12-0", "7/4F", "T R Gretton", "J J Burke"),
        ("3", "Star Flyer", 6, "12-0", "5/2", "W Greatrex", "James Bowen"),
        ("4", "Eurkash", 9, "10-11", "7/1", "P R Webber", "Liam Harrison"),
        ("PU", "Rolling Clouds", 7, "10-6", "5/1", "M Keighley", "James Best"),
        ("PU", "Moroval", 12, "10-2", "66/1", "Tracey Leeson", "James Turner")]),

    ("891051", "2025-11-25", "14:25", "Golf And Gallop Maiden Hurdle (GBB Race)", 4, "1m7f182y", "Good To Soft", 11, [
        ("1", "Next Twist", 5, "11-4", "13/8", "T O Murphy", "J S Bowen"),
        ("2", "Precious Metal", 4, "11-4", "6/5F", "Miss H C Knight", "Lily Pinchin"),
        ("3", "Nosy Neighbour", 4, "11-4", "16/1", "R Menzies", "Nathan Moscrop"),
        ("4", "Media Mogul", 4, "11-4", "9/2", "Tom Dascombe", "David Bass"),
        ("7", "Madajovy", 5, "11-4", "14/1", "D Skelton", "Tristan Durrell")]),
    ("831313", "2024-11-26", "14:10", "Download The At The Races App Maiden Hurdle (GBB Race)", 4, "1m7f182y", "Good (Good To Soft In Places)", 8, [
        ("1", "Achille Des Rocs", 5, "11-4", "7/1", "L Morgan", "Adam Wedge"),
        ("2", "Moonshine Man", 5, "11-4", "9/1", "Miss H C Knight", "Brendan Powell"),
        ("3", "Sergeant Fury", 4, "11-4", "15/8F", "Harry Derham", "Paul O'Brien"),
        ("4", "Dinofromberlais", 4, "11-4", "11/2", "O Murphy", "S Bowen"),
        ("6", "King Ulanda", 4, "11-4", "9/4", "O Greenall & J Guerriero", "Henry Brooke")]),
    ("714707", "2022-11-29", "14:35", "Follow vickersracing On Twitter Maiden Hurdle (GBB Race)", 4, "1m7f182y", "Good (Good To Soft In Places)", 14, [
        ("1", "Red Dirt Road", 5, "11-4", "6/4F", "J & A O'Neill", "Jonjo O'Neill Jr."),
        ("2", "Mrs Grimley", 4, "10-11", "2/1", "B Pauling", "Kielan Woods"),
        ("3", "Bobby Socks", 5, "11-4", "12/1", "O Murphy", "W T Kennedy"),
        ("4", "Shandancer", 5, "11-4", "10/1", "Miss A Murphy", "J J Burke")]),

    ("891052", "2025-11-25", "15:00", "Sky Sports Racing Virgin 519 Novices' Limited Handicap Hurdle", 5, "1m7f182y", "Good To Soft", 8, [
        ("1", "Secret Vino", 5, "11-12", "11/2", "T Ellis", "Jack Andrews"),
        ("2", "Hello Sweety", 4, "10-9", "13/2", "S Edmunds", "Charlie Hammond"),
        ("3", "Little Venice", 4, "11-5", "7/1", "N P Mulholland", "C O'Farrell"),
        ("4", "Pottersmattyeeehaa", 4, "11-7", "14/1", "M Crawley", "J M Quinlan"),
        ("5", "Lone Soldier", 7, "10-11", "33/1", "C & A Pogson", "C J Todd"),
        ("6", "One Million Dreams", 5, "11-12", "11/2", "Michael Keady", "S Bowen"),
        ("7", "Platenium", 6, "11-4", "5/2F", "S England", "Kielan Woods"),
        ("F", "Johnny Boom", 7, "11-8", "4/1", "S Lycett", "Lily Pinchin")]),
    ("831315", "2024-11-26", "15:10", "Sky Sports Racing Virgin 535 Novices' Limited Handicap Hurdle", 5, "1m7f182y", "Good (Good To Soft In Places)", 13, [
        ("1", "Neigh Botha", None, "", "2/1F", "O Greenall & J Guerriero", "Henry Brooke"),
        ("2", "Runaway Train", None, "", "11/2", "James Owen", "Mr Alex Chadwick"),
        ("3", "Window Of Time", None, "", "10/1", "A M Hales", "Kielan Woods")]),
    ("771088", "2023-11-28", "15:10", "Best Odds Guaranteed At PlanetSportBet Novices' Handicap Hurdle", 5, "1m7f182y", "Heavy (Soft In Places)", 4, [
        ("1", "Jack's A Legend", 8, "11-11", "85/40", "A E Jones", "Charlie Deutsch"),
        ("2", "Ring Of Beara", 4, "12-0", "11/8F", "T D Easterby", "Jamie Hamilton"),
        ("3", "Ferrybridge", 5, "11-4", "9/4", "James Owen", "Jamie Gambin"),
        ("4", "Royal Max", 5, "11-8", "20/1", "C & A Pogson", "C J Todd")]),

    ("891050", "2025-11-25", "13:50", "Join Southwell Golf Club Novices' Handicap Hurdle (GBB Race)", 4, "2m4f88y", "Good To Soft", 5, [
        ("1", "Nazare", 5, "11-7", "5/6F", "James Owen", "S Bowen"),
        ("2", "Havefunontherun", 5, "11-9", "7/1", "F O'Brien", "Tom Broughton"),
        ("3", "Jacques Clouseau", 6, "11-5", "12/1", "Mrs M Rowley", "Charlie Deutsch"),
        ("4", "Diamond Koda", 6, "11-5", "7/1", "N Kent", "Charlie Hammond"),
        ("5", "Moab", 5, "11-2", "10/3", "Miss H C Knight", "R T Dunne")]),
    ("831312", "2024-11-26", "13:40", "Watch Unbridled On attheraces.com Novices' Handicap Hurdle (GBB Race)", 4, "2m4f88y", "Good (Good To Soft In Places)", 8, [
        ("1", "Broughshane", 6, "12-0", "10/3", "J & A O'Neill", "Jonjo O'Neill Jr."),
        ("2", "Solar System", 5, "11-9", "8/13F", "P Hobbs & J White", "Callum Pritchard"),
        ("3", "Lexie's Moon", 6, "12-0", "25/1", "L Horsfall", "K Brogan"),
        ("4", "Manowest", 6, "11-10", "28/1", "O Murphy", "S Bowen"),
        ("5", "Red Panda", 5, "11-4", "25/1", "C E Longsdon", "Lily Pinchin"),
        ("PU", "Asian Star", 5, "11-12", "11/2", "D Skelton", "Harry Skelton"),
        ("PU", "Natchez Trace", 7, "10-13", "50/1", "D Carroll", "R T Dunne"),
        ("F", "Fat Harry", 7, "10-11", "40/1", "J Parkinson & S Smith", "Nick Scholfield")]),
    # distractor: same day 2m4f mares' handicap hurdle, class 5
    ("831314", "2024-11-26", "14:40", "Sky Sports Racing Sky 415 Mares' Handicap Hurdle", 5, "2m4f88y", "Good (Good To Soft In Places)", 6, [
        ("1", "Rockola", None, "", "5/4F", "A King", "Tom Cannon")]),
    ("771089", "2023-11-28", "15:40", "Get Emma's Offers At PlanetSportBet Novices' Handicap Hurdle (GBB Race)", 4, "2m4f88y", "Heavy (Soft In Places)", 4, [
        ("1", "Aristobulus", 4, "10-10", "11/1", "S Edmunds", "C Gethings"),
        ("2", "Hill Of Tara", 6, "10-6", "2/7F", "Miss V Williams", "Charlie Deutsch"),
        ("3", "Godot", 6, "12-1", "5/1", "A Irvine", "Tom Cannon"),
        ("PU", "Tessy Lad", 4, "11-5", "20/1", "S England", "Jonathan England")]),
    ("714709", "2022-11-29", "15:35", "Download The Vickers.Bet App Handicap Hurdle", 5, "2m4f88y", "Good (Good To Soft In Places)", 12, [
        ("1", "Sporting Mike", 5, "12-1", "9/4", "B Pauling", "Kielan Woods"),
        ("2", "Samatian", 5, "10-10", "7/4F", "K Bailey & M Nicholls", "David Bass"),
        ("3", "Balinesker Beach", 7, "10-11", "10/1", "N P Mulholland", "Sam Twiston-Davies"),
        ("4", "Ballyfarsoon", 11, "10-2", "50/1", "P Winks", "Charlie Price")]),

    ("891053", "2025-11-25", "15:35", "Free Tips Daily On attheraces.com Conditional Jockeys' Handicap Hurdle", 5, "3m60y", "Good To Soft", 8, [
        ("1", "Apieceovfortune", 5, "10-12", "8/1", "Mrs P Sly", "Jack Andrews"),
        ("2", "East Eagle", 5, "10-9", "9/2", "M E Sowerby", "Charlie Maggs"),
        ("3", "Zoffalee", 10, "11-0", "20/1", "M E Sowerby", "William Maggs"),
        ("4", "Max's Champ", 9, "12-0", "16/1", "S Drinkwater", "Benjamin Macey"),
        ("F", "Ruler Legend", 6, "11-6", "5/1", "D Carroll", "Peter Kavanagh"),
        ("R", "Captain Trigger", 5, "10-10", "11/10F", "R L Llewellyn", "Charlie Price"),
        ("PU", "Ghost Pepper", 5, "10-2", "15/2", "D J Jeffreys", "Jamie Brace"),
        ("PU", "As Good As Can Be", 5, "10-2", "66/1", "Miss C Dyson", "Alice Stevens")]),
    ("831316", "2024-11-26", "15:40", "Free Tips Daily On attheraces.com Conditional Jockeys' Handicap Hurdle", 5, "3m60y", "Good (Good To Soft In Places)", 6, [
        ("1", "Lunar Contact", 6, "12-0", "8/13F", "T Ellis", "Callum Pritchard"),
        ("2", "Mrs Tabitha", 5, "11-6", "7/2", "O Greenall & J Guerriero", "Ben Smith"),
        ("3", "Mackie Dee", 12, "10-7", "12/1", "R J Armson", "Philip Armson"),
        ("4", "Bergentown", 7, "11-2", "9/1", "J Candlish", "Gearoid Harney"),
        ("5", "Mystic Man", 7, "11-4", "50/1", "R Potter", "Dylan Johnston"),
        ("6", "You Say Its Over", 6, "10-9", "11/1", "Micky Hammond", "Joshua Thompson")]),
    ("771086", "2023-11-28", "14:10", "Bet & Watch At planetsportbet.com Conditional Jockeys' Handicap Hurdle", 4, "3m60y", "Heavy (Soft In Places)", 3, [
        ("1", "Stratton Oakmont", 7, "11-2", "5/4J", "K Woollacott", "Ben Godfrey"),
        ("2", "Mountain Leopard", 8, "11-6", "5/4J", "Miss V Williams", "Ned Fox"),
        ("3", "Our Bill's Aunt", 7, "11-7", "9/2", "A M Hales", "Harriet Tucker")]),
    ("714708", "2022-11-29", "15:05", "Follow Vickers.Bet For Tommo's Daily Tips Handicap Hurdle", 4, "3m60y", "Good (Good To Soft In Places)", 7, [
        ("1", "Docpickedme", 6, "12-0", "13/2", "H Whittington", "G Sheehan"),
        ("2", "Sporting Ace", 6, "11-11", "5/2", "N B King", "J M Quinlan"),
        ("3", "Jen's Boy", 8, "11-10", "14/1", "N J Henderson", "N de Boinville"),
        ("4", "Bignorm", 10, "10-2", "66/1", "Mrs R Gasson", "Benjamin Poste"),
        ("F", "Snipe", None, "", "85/40F", "D Skelton", "Harry Skelton")]),
]

TYPE = lambda name: "Chase" if "Chase" in name else "Hurdle"

# Tomorrow's card (Racing Post, 24 Nov 2026): (race_id, off, name, class, dist, [(no, horse, age, wt, or, trainer, jockey, form)])
CARD = [
    ("931639", "11:56", "Join The Southwell Racecourse Corporate Club Handicap Chase", 5, "2m4f88y", [
        (1, "Rap Soul (FR)", 7, "12-0", 98, "Richard J Bandey", "Jack Quinlan", "0113-P"),
        (2, "Imperial Bede (FR)", 8, "11-10", 94, "Jonjo & A J O'Neill", "Jonjo O'Neill Jr", "443683"),
        (3, "Grain Trade", 7, "11-8", 92, "Billy Aprahamian", "Robert Dunne", "44F-37"),
        (4, "The Paddy Pie (IRE)", 13, "11-6", 90, "Joel Parkinson & Sue Smith", "Oscar Palmer", "35-437"),
        (5, "Henry Box Brown (IRE)", 9, "10-13", 83, "Mrs C Williams", "James Turner", "-U6163"),
        (6, "Bravethewaves", 9, "10-12", 82, "Oliver Greenall & Josh Guerriero", "Toby Wynne", "75-03P"),
        (7, "Four Decades", 5, "10-9", 79, "T Ellis", "Finn Lambert", "-8863P"),
        (8, "Colby Mayfield (IRE)", 6, "10-9", 79, "John & Rhys Flint", "Adam Wedge", "935-U6"),
        (9, "Dynamite Defense (IRE)", 5, "10-2", 72, "Sarah-Jayne Davies", "James Best", "U3P530"),
        (10, "Doors Breaker (FR)", 9, "10-2", 72, "David Pipe", "Jack Tudor", "3/P0P/")]),
    ("931638", "12:26", "Dance Through The Decades Christmas Parties Novices' Handicap Chase", 5, "3m60y", [
        (1, "Vicomte Le Brave (FR)", 7, "12-0", 100, "Cynthia Woods", "Rian Corcoran", "-3P356"),
        (2, "Sledgehammer (IRE)", 6, "11-13", 99, "Adrian Paul Keatley", "Oakley Brown", "-64F11"),
        (3, "Danger Nap (IRE)", 5, "11-13", 99, "Jonjo & A J O'Neill", "Jonjo O'Neill Jr", "6P4-23"),
        (4, "Kastellion (FR)", 6, "11-13", 99, "Mel Rowley", "Charlie Deutsch", "6343-4"),
        (5, "Peckforton Hills (IRE)", 6, "11-5", 91, "Oliver Greenall & Josh Guerriero", "Jack Tudor", "73222-"),
        (6, "Bells Of Ufford (IRE)", 6, "11-2", 88, "Mitchell Hunt & Tim Vaughan", "David Noonan", "4-2542"),
        (7, "Could Be You (IRE)", 6, "10-9", 81, "Neil Mulholland", "Richie McLernon", "9-F851"),
        (8, "Scoro (FR)", 6, "10-2", 74, "L J Morgan", "Harry Reed", "664PP7"),
        (9, "Illico De Montave (FR)", 8, "10-2", 74, "Rosemary Gasson", "Ben Poste", "/07-89")]),
    ("931636", "12:56", "Winter Ladies Night Saturday 28th November Maiden Hurdle (GBB Race) (Div I)", 4, "1m7f182y", [
        (1, "Ballyboy Prince (FR)", 4, "11-4", None, "Dan Skelton", "Harry Skelton", "UU-6"),
        (2, "Beau De Maine (FR)", 4, "11-4", None, "Nigel & Willy Twiston-Davies", "Sam Twiston-Davies", ""),
        (3, "Delusionofgrandeur (IRE)", 5, "11-4", None, "Fergal O'Brien", "Kielan Woods", "P62-28"),
        (4, "Dressforsuccess (IRE)", 4, "11-4", None, "Dan Skelton", "Tristan Durrell", ""),
        (5, "Grandorado (IRE)", 6, "11-4", None, "David Pipe", "Jack Tudor", "UP21-"),
        (6, "Imperial Sea (IRE)", 5, "11-4", None, "Charles & Adam Pogson", "Robert Dunne", "5-0"),
        (7, "Shah (FR)", 5, "11-4", None, "Sam England", "Jonathan England", "5-2177"),
        (8, "Tandy's Bridge (IRE)", 5, "11-4", None, "T Ellis", "Finn Lambert", "204-0"),
        (9, "Uda Man Dan (GER)", 4, "11-4", None, "Dan Skelton", "Jonathan Burke", ""),
        (10, "Who's The Goat (IRE)", 6, "11-4", None, "Micky Hammond & Becky Smith", "Conor O'Farrell", "U"),
        (11, "Lady Tara", 7, "10-11", None, "Richard Phillips", "Adam Wedge", ""),
        (12, "Popton Point (IRE)", 5, "10-11", None, "Jennie Candlish", "Luke Scott", "112-")]),
    ("934164", "13:26", "Winter Ladies Night Saturday 28th November Maiden Hurdle (GBB Race) (Div II)", 4, "1m7f182y", [
        (1, "Avatar Jet (IRE)", 5, "11-4", None, "Declan Carroll", "Oakley Brown", "P4"),
        (2, "Campfield Flyer", 4, "11-4", None, "Dr Richard Newland", "Luke Scott", "62P-"),
        (3, "Chilly Breeze", 4, "11-4", None, "Michael Chapman", "Philip Armson", ""),
        (4, "Gettothebar", 4, "11-4", None, "Dan Skelton", "Tristan Durrell", "0"),
        (5, "Goodbye Earl (IRE)", 4, "11-4", None, "David Pipe", "Rian Corcoran", "31-3"),
        (6, "Made In Reugny (FR)", 4, "11-4", None, "Dan Skelton", "Harry Skelton", "2-"),
        (7, "Riptide (IRE)", 4, "11-4", None, "David Pipe", "Jack Tudor", "16"),
        (8, "The Two Four (IRE)", 5, "11-4", None, "Christian Williams", "Adam Wedge", "2-P"),
        (9, "Thunder Thief (IRE)", 4, "11-4", None, "Dan Skelton", "Charlie Todd", "P0"),
        (10, "Yafaarr (IRE)", 4, "11-4", None, "Sam England", "Jonathan England", "8"),
        (11, "Dave's Sister", 7, "10-11", None, "D J Jeffreys", "Daire McConville", "/2F-32"),
        (12, "Look This Way", 4, "10-11", None, "Tom Ward", "Charlie Deutsch", "0-9")]),
    ("931641", "13:56", "Festive Fixtures At Southwell Racecourse Novices' Limited Handicap Hurdle", 5, "1m7f182y", [
        (1, "Gaelic Glow", 5, "11-12", 95, "Sam England", "Jonathan England", "565-47"),
        (2, "Trackman", 6, "11-8", 91, "Simon Pearce", "Jack Quinlan", "658"),
        (3, "Troy Story", 4, "11-8", 91, "Dave Roberts", "Lee Edwards", "055"),
        (4, "Yourcardismarked (IRE)", 5, "11-7", 90, "Jennie Candlish", "Sean Quinlan", "05805-"),
        (5, "Milady Du Breuil (FR)", 4, "11-7", 90, "Christian Williams", "Jack Tudor", "6454F-"),
        (6, "Dino Bellagio", 7, "11-7", 90, "Donald McCain", "Brian Hughes", "4847/3"),
        (7, "Laplander", 4, "11-6", 89, "Tom Ward", "Sean Bowen", "6454-"),
        (8, "Everest", 7, "11-5", 88, "Jamie Moore & Josh Moore", "Caoilin Quinn", "374P-4"),
        (9, "Tenadaay", 4, "11-3", 86, "Fergal O'Brien", "Kielan Woods", "37-9"),
        (10, "Little Lady Lucy (IRE)", 5, "11-2", 85, "Neil Mulholland", "Laurie Gallacher", "11-297"),
        (11, "Cheap Sandwiches (IRE)", 5, "11-1", 84, "Chris Gordon", "Freddie Gordon", "445-56"),
        (12, "Orbys River (IRE)", 8, "10-13", 82, "Sam Allwood", "Toby Wynne", "12715/"),
        (13, "On Subs (FR)", 4, "10-11", 80, "Christian Williams", "Adam Wedge", "8-59"),
        (14, "Nobody Told Me", 6, "10-5", 74, "Dan Skelton", "Harry Skelton", "75543-")]),
    ("931637", "14:26", "Christmas Jumper Day Sunday 13th December Handicap Hurdle", 4, "2m4f88y", [
        (1, "Magical Arthur (IRE)", 8, "12-0", 110, "Jennie Candlish", "Sean Quinlan", "2P/01-"),
        (2, "At Mangan Bridge (IRE)", 8, "11-12", 108, "Stuart Edmunds", "Charlie Hammond", "3511-0"),
        (3, "Ballin Bay (IRE)", 8, "11-12", 108, "Rebecca Menzies", "Shane Fitzgerald", "41117-"),
        (4, "Ka Mate Du Brivet (FR)", 5, "11-12", 108, "Warren Greatrex", "Caoilin Quinn", "7192-2"),
        (5, "The Boss Bear (IRE)", 6, "11-11", 107, "James Owen", "Jonathan Burke", "2P88-4"),
        (6, "Starshine Legend (IRE)", 5, "11-9", 105, "Sarah-Jayne Davies", "James Best", "35715"),
        (7, "Blazing Duke (IRE)", 5, "11-9", 105, "Oliver Greenall & Josh Guerriero", "Jack Tudor", "/57U3-"),
        (8, "Presenting Milan (IRE)", 6, "11-8", 104, "Robert Hawker", "Jonjo O'Neill Jr", "62/1-3"),
        (9, "Typhoon Warrior (IRE)", 5, "11-8", 104, "Dan Skelton", "Harry Skelton", "4366-9"),
        (10, "Eternity Rose", 5, "11-6", 102, "Fergal O'Brien", "Liam Harrison", "3053-4"),
        (11, "In The Purple (IRE)", 5, "11-6", 102, "Olly Murphy", "Sean Bowen", "87001-"),
        (12, "Stroll On By (IRE)", 9, "11-5", 101, "Charlie Longsdon", "Brian Hughes", "55FU-4"),
        (13, "Ithaka (IRE)", 10, "11-5", 101, "Alastair Ralph", "Ciaran Gethings", "1PPF-P"),
        (14, "Smile Back (IRE)", 6, "11-4", 100, "Richard Phillips", "Adam Wedge", "22634-"),
        (15, "Laysoft (IRE)", 4, "11-2", 99, "Joel Parkinson & Sue Smith", "Peter Kavanagh", "3235-3")]),
    ("931640", "14:56", "Book The Bistro In Seasons Restaurant Handicap Hurdle", 5, "3m60y", [
        (1, "Has Troke (FR)", 9, "12-0", 100, "Alex Hales", "Kielan Woods", "1/357-"),
        (2, "Harrys Hope (IRE)", 8, "11-13", 99, "Matt Crawley", "Jack Quinlan", "-24243"),
        (3, "Gimarias (IRE)", 6, "11-12", 98, "Mel Rowley", "Toby Wynne", "F753-2"),
        (4, "Innisfree Lass (IRE)", 8, "11-10", 96, "Joey Ramsden", "Harry Atkins", "5315-P"),
        (5, "The Brave Guy (IRE)", 6, "11-7", 93, "Jennie Candlish", "Sean Quinlan", "/79-56"),
        (6, "Eyeeye", 6, "11-0", 86, "Clare Ellam", "Mr Henry Bailey", "950847"),
        (7, "Ocean Walz (FR)", 6, "10-13", 85, "Rosemary Gasson", "Ben Poste", "68286-"),
        (8, "Elusive Shine (IRE)", 6, "10-12", 84, "Sam England", "Jonathan England", "698t1"),
        (9, "Twp Stori", 8, "10-9", 81, "Samuel Drinkwater", "Philip Armson", "56-332")]),
    ("931635", "15:26", "Conferences And Events At Southwell Racecourse Handicap Hurdle", 3, "1m7f182y", [
        (1, "Manuelito", 6, "12-0", 128, "Philip Hobbs & Johnson White", "Ben Jones", "9/1F-4"),
        (2, "The Cistercian (IRE)", 6, "11-10", 124, "Stuart Edmunds", "Charlie Hammond", "3U3U2-"),
        (3, "Wild Goose (IRE)", 6, "11-10", 124, "Kim Bailey & Mat Nicholls", "Aamilah Aswat", "21-514"),
        (4, "Lawrenny", 7, "11-9", 123, "Jennie Candlish", "Sean Quinlan", "1/P5-4"),
        (5, "Klitschko", 8, "11-3", 117, "Lucinda Hughes", "Brian Hughes", "U1-422"),
        (6, "Saligo Bay (IRE)", 8, "11-1", 115, "Sam England", "Jonathan England", "5-8PP6"),
        (7, "Mister Cessna (FR)", 5, "10-13", 113, "Fergal O'Brien", "Fern O'Brien", "64-74V"),
        (8, "He's A Latchico (IRE)", 8, "10-12", 112, "Jamie Moore & Josh Moore", "Caoilin Quinn", "2U3-58")]),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    cols = ["date", "region", "course_id", "course", "race_id", "off", "race_name", "type", "class",
            "dist", "going", "ran", "pos", "horse", "age", "lbs", "sp", "trainer", "jockey"]
    with open(os.path.join(OUT, "southwell_history.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for rid, d, off, name, cls, dist, going, ran, rows in PAST:
            for pos, horse, age, wt, sp, tr, jk in rows:
                w.writerow([d, "gb", "61", "Southwell", rid, off, name, TYPE(name), f"Class {cls}", dist,
                            going, ran, pos, horse, age or "", lbs(wt) if wt else "", sp, tr, jk])
    races = {}
    for rid, off, name, cls, dist, runners in CARD:
        races[off] = {
            "race_id": rid, "course": "Southwell", "course_id": "61", "region": "GB", "date": "2026-11-24",
            "off_time": off, "race_name": name, "race_class": f"Class {cls}", "type": TYPE(name),
            "distance": dist, "going": "Good", "surface": "Turf",
            "runners": [{"number": n, "name": h, "age": a, "lbs": lbs(wt), "ofr": o, "trainer": t,
                         "jockey": j, "form": f} for n, h, a, wt, o, t, j, f in runners],
        }
    with open(os.path.join(OUT, "southwell_racecards_2026-11-24.json"), "w", encoding="utf-8") as fh:
        json.dump({"GB": {"Southwell": races}}, fh, indent=1)
    print("fixtures written")


if __name__ == "__main__":
    main()
