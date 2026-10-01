# VDL notehead guide

Which notehead plays each sound of the Virtual Drumline (VDL) Sibelius
template's drumline battery: snares, tenors, basses and cymbal line.
Transcribed from _VDL Maps 7.0a_ (Sibelius VDL Template 7.0a, May 2012,
© 2012 Hugh Smith, distributed by The Write Score), used with
permission for documentation. The template's own PDF remains the
reference; check it when this guide and the score disagree.

## How noteheads pick sounds

Every VDL instrument is a custom Sibelius percussion instrument. Its
sounds are told apart by **notehead number** (Sibelius notehead style)
and staff position. Many of the noteheads look alike: a right-hand hit
is notehead 0 and a left-hand hit notehead 31, both ordinary filled
noteheads, but they play different samples. When two sounds share a
notehead number (a rim and a backstick, say), the staff position tells
them apart.

To get a sound, give each note the sound's notehead number in
`write_live_passage` (its events take a `notehead` number), which writes
a whole passage in one call. To change notes already written, use
`set_live_notehead` (it takes a number as well as a shape name) and pass
`beat` to change only the note on one beat or partial, such as `"2&"` or
`"1let"`. Read the passage back with `read_passage` to check.

- **Manual and AutoRL.** _Manual_ instruments have a left-hand and a
  right-hand notehead for each stroke (listed L / R below). _AutoRL_
  instruments use one notehead per sound and alternate the hands in
  playback.
- **Rolls.** Sustained buzz rolls are notehead 20, or notehead 0 with a
  buzz (z on the stem, `set_live_tremolo(kind="buzz")`). The crescendo
  and decrescendo roll noteheads are written with a buzz. Sounds the
  template draws with tremolo strokes (stirs, ride and hi-hat rolls,
  rebound doubles) take 2 or 3 strokes with `set_live_tremolo`.
- **Crushes** are written as two noteheads: the attack, or the crush
  with a buzz.

## Snare Solo Kevlar

| Sound           | L   | R   |
| --------------- | --- | --- |
| Hit             | 31  | 0   |
| Hit crossover   | 50  | 49  |
| Shot            | 51  | 29  |
| Rim             | 40  | 1   |
| Backstick       | 63  | 22  |
| Butt (vertical) | 63  | 22  |
| Rod             | 62  | 6   |
| Dread           | 58  | 14  |
| Felt            | 59  | 15  |
| On cage         | 40  | 1   |

| Sound                              | Notehead              |
| ---------------------------------- | --------------------- |
| Ping Shot                          | 30                    |
| OTH Double Shots                   | 52                    |
| Rim Knock                          | 11                    |
| Stick Shot HIGH                    | 55                    |
| Stick Shot LOW                     | 12                    |
| Friction Slide 1                   | 34                    |
| Friction Slide 2                   | 35                    |
| Stick Snap                         | 2                     |
| Dry Crush                          | 32, or 0 with a buzz  |
| Fat Crush                          | 33, or 31 with a buzz |
| Sustained buzz roll                | 20 (or 0 with a buzz) |
| fp Sustained roll                  | 39                    |
| Short / Medium / Long Decresc roll | 31 / 33 / 35          |
| Short / Medium / Long Cresc roll   | 32 / 34 / 36          |
| Stick on Stick Rebound Doubles     | 18 (tremolo)          |
| Rim Buzz Roll                      | 41 (tremolo)          |
| Twisting Motion Rim Roll           | 2 (tremolo)           |

## Snare Solo Mylar

As Snare Solo Kevlar, plus:

| Sound                                | Notehead |
| ------------------------------------ | -------- |
| Throwoff (snares on or off)          | 2        |
| Edge Rebound L / R (snares off only) | 57 / 21  |

The fp Sustained roll (39) exists with the snares on only.

## SnareLine Manual

Also SnareLine Manual LITE. Snare sounds:

| Sound                    | L   | R   |
| ------------------------ | --- | --- |
| Hit                      | 31  | 0   |
| Hit crossover            | 50  | 49  |
| Shot                     | 51  | 29  |
| Rim                      | 40  | 1   |
| Backstick                | 63  | 22  |
| Rod                      | 62  | 6   |
| Dread                    | 58  | 14  |
| Solo snare Hit           | 31  | 0   |
| Solo snare Hit crossover | 50  | 49  |
| Solo snare Shot          | 51  | 29  |

| Sound                           | Notehead              |
| ------------------------------- | --------------------- |
| Ping Shot                       | 30                    |
| OTH Double Shot                 | 52                    |
| Rim Knock                       | 11                    |
| Stick Shot                      | 12                    |
| Stick Click                     | 1                     |
| Throwoff                        | 2                     |
| Dry Crush (also solo snare)     | 32, or 0 with a buzz  |
| Fat Crush (also solo snare)     | 33, or 31 with a buzz |
| Sustained buzz roll             | 20 (or 0 with a buzz) |
| fp Sustained roll               | 39                    |
| Short / Med / Long Decresc roll | 31 / 33 / 35          |
| Short / Med / Long Cresc roll   | 32 / 34 / 36          |

Other sounds on the staff:

| Sound                       | Notehead                            |
| --------------------------- | ----------------------------------- |
| Metronome, Metronome Accent | 19                                  |
| Sticks In                   | 21                                  |
| Vocal "Dut" 2 / 1           | 15 / 59                             |
| Snare Shell                 | 17                                  |
| Dress Center Harness Hit    | 29                                  |
| Cymbal Crash                | 1                                   |
| Ride Cym roll               | 40, or 1 with tremolo strokes       |
| Ride Cym bell               | 6                                   |
| Ride Cym hit                | 1                                   |
| Hi Hat press roll           | 45, or 1 or 40 with tremolo strokes |
| Hi Hat Tight L / R          | 40 / 1                              |
| Hi Hat Med L / R            | 42 / 41                             |
| Hi Hat Loose L / R          | 44 / 43                             |
| Cowbell w/Tip               | 54                                  |
| Cowbell Mouth               | 16                                  |
| Ribbon Crasher              | 23                                  |

## SnareLine (AutoRL)

One notehead per sound; the hands alternate in playback. The roll
noteheads are numbered differently from SnareLine Manual.

| Sound                                | Notehead                      |
| ------------------------------------ | ----------------------------- |
| Hits                                 | 0                             |
| Hits crossovers                      | 49                            |
| Shots                                | 29                            |
| Ping Shot                            | 30                            |
| OTH Double Shot                      | 52                            |
| Rim Knock                            | 11                            |
| Stick Shot                           | 12                            |
| Rims                                 | 1                             |
| Stick Click                          | 1                             |
| Backsticks                           | 22                            |
| Rods                                 | 6                             |
| Dreads                               | 14                            |
| Throwoff                             | 2                             |
| Dry Crush                            | 32, or 0 with a buzz          |
| Fat Crush                            | 33                            |
| Sustained buzz roll                  | 20 (or 0 with a buzz)         |
| fp Sustained roll                    | 39                            |
| Decresc SHORT / MEDIUM / LONG roll   | 31 / 32 / 33                  |
| Cresc LONG / MEDIUM / SHORT roll     | 34 / 35 / 36                  |
| Solo snare Hits / crossovers / Shots | 0 / 49 / 29                   |
| Solo snare Dry Crush / Fat Crush     | 32 (or 0 with a buzz) / 33    |
| Ride Cym roll                        | 40, or 1 with tremolo strokes |
| Ride Cym bell / hit                  | 6 / 1                         |
| Hi Hat press roll                    | 45, or 1 with tremolo strokes |
| Hi Hat Tight / Med / Loose           | 1 / 41 / 43                   |
| Metronome, Metronome Accent          | 19                            |
| Sticks In                            | 21                            |
| Vocal "Dut" 2 / 1                    | 15 / 59                       |
| Snare Shell                          | 17                            |
| Dress Center Harness Hit             | 29                            |
| Cymbal Crash                         | 1                             |

## TenorLine Manual

Also TenorLine Manual LITE. The same noteheads serve every drum (D4,
the lowest, to D1, and the spocks Sp2 and Sp1); the staff position
picks the drum.

| Sound         | L   | R   |
| ------------- | --- | --- |
| Hit           | 31  | 0   |
| Hit crossover | 50  | 49  |
| Shot          | 51  | 29  |
| Dread         | 58  | 14  |
| Rod           | 62  | 6   |
| Rim           | 40  | 1   |
| Rod on Rim    | 63  | 22  |

| Sound                 | Notehead              |
| --------------------- | --------------------- |
| Crush, dry            | 32, or 0 with a buzz  |
| Crush, fat            | 33, or 31 with a buzz |
| Sustained buzz roll   | 20 (or 0 with a buzz) |
| Decrescendo buzz roll | 35                    |
| Crescendo buzz roll   | 36                    |
| "Snenor"              | 19                    |
| Stick Shot            | 12                    |
| Dread Stir            | 2 (tremolo)           |
| "Duts"                | 15                    |
| Muted Taps            | 10, 31 or 0           |
| Hand Muffle           | 17 or 0               |
| Skank                 | 52 or 29              |
| Cowbell               | 16                    |
| Hand Claps            | 6                     |
| Low / High Jam Block  | 15                    |
| Mallet Click          | 1                     |
| Double Stop on Shells | 30                    |
| Stand Hit             | 15                    |

## TenorLine (AutoRL)

One notehead per sound; the hands alternate in playback.

| Sound                 | Notehead              |
| --------------------- | --------------------- |
| Hits                  | 0                     |
| Crossovers            | 49                    |
| Shots                 | 29                    |
| Dreads                | 14                    |
| Rods                  | 6                     |
| Rims                  | 1                     |
| Rods on Rim           | 22                    |
| Crush, dry            | 32, or 0 with a buzz  |
| Crush, wet            | 33                    |
| Sustained buzz roll   | 20 (or 0 with a buzz) |
| Decrescendo buzz roll | 35                    |
| Crescendo buzz roll   | 36                    |
| Snenor                | 19                    |
| Dread Stir            | 2 (tremolo)           |
| "Duts"                | 15                    |
| Muted Taps            | 10 or 0               |
| Hand Muffle           | 17 or 0               |
| Skank                 | 52 or 29              |
| Cowbell               | 16                    |
| Hand Claps            | 6                     |
| Low / High Jam Block  | 15                    |
| Mallet Click          | 1                     |
| Double Stop on Shells | 30                    |
| Stand Hit             | 15                    |

## Tenor Solo

As TenorLine Manual (Hit, crossover, Shot, Dread, Rod, Rim, Rod on Rim,
buzz rolls, Snenor and Stick Shot use the same noteheads), with:

| Sound                       | Notehead              |
| --------------------------- | --------------------- |
| Crush L                     | 33, or 31 with a buzz |
| Crush R                     | 32, or 0 with a buzz  |
| Skank Late Muffle           | 53 or 51              |
| D4 Shell, D3 Shell          | 30                    |
| Double Stop on Lower Shells | 30                    |
| Cowbell                     | 16                    |
| Low / High Jam Block        | 15                    |

Tenor Solo has no Dread Stir, Hand Claps, Mallet Click or Stand Hit.

## BassLine Manual

Also BassLine Manual LITE. The same noteheads serve every drum (D6, the
lowest, to D1); the staff position picks the drum.

| Sound | L   | R   |
| ----- | --- | --- |
| Hit   | 31  | 0   |
| Rim   | 40  | 1   |
| Shot  | 51  | 29  |
| Dread | 58  | 14  |
| Rod   | 62  | 6   |

| Sound                 | Notehead                 |
| --------------------- | ------------------------ |
| Crush                 | 32, or 0 with a buzz     |
| Mute w/LH             | 33, or 0 with a staccato |
| Sustained buzz roll   | 20 (or 0 with a buzz)    |
| Decrescendo buzz roll | 35                       |
| Crescendo buzz roll   | 36                       |
| Roll w/ Dread         | 14 (tremolo)             |
| Roll w/ Rod           | 6 (tremolo)              |
| Rim w/ Dread          | 19                       |
| Rim w/ Rod            | 23                       |
| "Dut!"                | 15                       |

Unison (the whole line on one note):

| Sound                 | Notehead              |
| --------------------- | --------------------- |
| Sticks In             | 21                    |
| Stick Click           | 1                     |
| Dread L / R           | 58 / 14               |
| Dread Roll            | 14 (tremolo)          |
| Dread Roll on Rim     | 19 (tremolo)          |
| Rim L / R             | 51 / 29               |
| Hit L / R             | 47 / 46               |
| Crush                 | 48, or 46 with a buzz |
| Sustained buzz roll   | 46 with a buzz        |
| Decrescendo buzz roll | 47                    |
| Crescendo buzz roll   | 48                    |
| Mute w/LH             | 46                    |

## BassLine (AutoRL)

One notehead per sound; the hands alternate in playback.

| Sound                      | Notehead              |
| -------------------------- | --------------------- |
| Hits                       | 0                     |
| Crush                      | 32, or 0 with a buzz  |
| Rims                       | 1                     |
| Rods                       | 6                     |
| Dreads                     | 14                    |
| Sustained buzz roll        | 20 (or 0 with a buzz) |
| "Dut!"                     | 15                    |
| Unison Sticks In           | 21                    |
| Unison Stick Click         | 1                     |
| Unison Rims                | 29                    |
| Unison Hits                | 46                    |
| Unison Sustained buzz roll | 47, or 46 with a buzz |
| Unison Crush               | 48, or 46 with a buzz |

## BassLine 10-Drums Manual

The same noteheads serve every drum (D10, the lowest, to D1).

| Sound | L   | R   |
| ----- | --- | --- |
| Hit   | 31  | 0   |
| Rim   | 40  | 1   |
| Dread | 58  | 14  |
| Rod   | 62  | 6   |

| Sound            | Notehead              |
| ---------------- | --------------------- |
| Crush            | 32, or 0 with a buzz  |
| Sustained roll   | 20 (or 0 with a buzz) |
| Unison Sticks In | 21                    |
| Unison Rim L / R | 51 / 29               |
| Unison Hit L / R | 47 / 46               |
| Unison Crush     | 48, or 46 with a buzz |
| Unison Buzz Roll | 46 with a buzz        |

## BassLine 10-Drums (AutoRL)

| Sound                 | Notehead              |
| --------------------- | --------------------- |
| Hits                  | 0                     |
| Rims                  | 1                     |
| Rods                  | 6                     |
| Dreads                | 14                    |
| Sustained roll        | 20 (or 0 with a buzz) |
| Unison Sticks In      | 21                    |
| Unison Rims           | 29                    |
| Unison Hits           | 46                    |
| Unison Sustained roll | 47, or 46 with a buzz |
| Unison Crush          | 48, or 46 with a buzz |

## Cymbal Line (All, 16in, 18in, 20in)

The noteheads are the same for every cymbal. In Cymbal Line All the
staff position picks the cymbal: from the bottom, 20" solo, 20" unison,
18" solo, 18" unison, 16" solo, 16" unison.

| Sound               | Notehead           |
| ------------------- | ------------------ |
| Whale Call          | 18                 |
| Tremolo             | 20 (tremolo)       |
| Circular Roll       | 36 (tremolo)       |
| Flat Roll           | 35 (tremolo)       |
| Port Crash          | 31                 |
| Orchestral Crash    | 0                  |
| Flat Crash          | 32                 |
| Crash Choke Secco   | 33                 |
| Crash Choke Fat     | 34                 |
| Vacuum Suck         | 51 with a staccato |
| Sizzle              | 51 with a tenuto   |
| Sizz/Suck A / B / C | 51 / 52 / 53       |
| Tap Choke           | 16 with a staccato |
| Tap Edge            | 16                 |
| Tap Halfway         | 54                 |
| Crunch Choke        | 40                 |
| Ding                | 17                 |
| HiHat Choke         | 41                 |
| Click               | 22                 |
| Slow Zing           | 56                 |
| Fast Zing           | 11                 |
| Scratch Out         | 6                  |
| Scratch In          | 62                 |

## Showstyle Single Tenors

| Sound         | L   | R   |
| ------------- | --- | --- |
| Hit           | 31  | 0   |
| Hit crossover | 50  | 49  |
| Rim           | 40  | 1   |

AutoRL: Hits 32, Rims 41.
