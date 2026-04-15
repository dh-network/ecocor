# Ecocor MD syntax
This document describes the markdown-like syntax for encoding novel structure in [txt](ecocorMD) for automatic conversion into eltec-style tei.

## Operators:

`#` - means here begins a new highest-order division of a book. If the book is divided in chapter -- then any chapter should begin with that. The first occurrence of a # marks the end of the front matter and the beginning of the text proper. If the book has no divisions, there should still be one first #. If the division has a title (e.g. Kapitel 1 or  'Der Kampf mit dem Höhlenlöwen', it should be in the same line as the # symbol)

Examples:



1. First division in [Rulaman](ecocorMD/ecocorMD_demo_samples/EzProse_Example_David_Friedrich_Weinland_-_Rulaman_(1878).txt):
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Aus grauer Vorzeit

Denn tausend Jahre sind vor dir wie der Tag, der gestern vergangen ist, und wie
eine Nachtwache.

Es war eine Zeit fragt nicht, vor wieviel tausend Jahren, niemand weiß es, da
war ein Meer, wo heute die Schwäbische Alb sich erhebt.

```


2. First (and only) division in [Theodor Storm's 'Von Kindern und Katzen, und wie sie die Nine begruben'](ecocorMD/ecocorMD_demo_samples/EzProse_Example_Theodor_Storm_-_Von_Kindern_und_Katzen_und_wie_sie_die_Nine_begruben_(1876).txt) -- here we just mark the beginning of the text proper, it will be the only division of the text:
```

Theodor Storm

Von Kindern und Katzen, und wie sie die Nine begruben

# 

Mit Katzen ist es in früherer Zeit in unserem Hause sehr »begänge« gewesen.
Noch vor meiner Hochzeit wurde mir von einem alten Hofbesitzer ein kleines
kaninchengraues Kätzchen ins Haus gebracht; er nahm es sorgsam aus seinem
zusammengeknüpften Schnupftuch, setzte es vor mir auf den Tisch und sagte: »Da
bring ich was zur Aussteuer!«

```

1. Fifth chapter in [Rulaman](ecocorMD/EzProse_Example_David_Friedrich_Weinland_-_Rulaman_(1878).txt):
```

Sicher und ohne Zaudern schritt Rul voran, denn er
kannte auch diese Pfade meilenweit von seiner Heimat so gut wie die bei der
Tulka.

# 5 Der Kampf mit dem Höhlenlöwen

Rul war etwa hundert Schritte im Wald gegangen, als er vom Pfad ab nach links
in das Dickicht einbog. Er hieß die anderen Männer warten und nahm nur Rulaman
an der Hand mit sich. 

```

N.B. that in the original `5` and  `Der Kampf mit dem Höhlenlöwen` were two separate lines. For our purposes, it's best to put the whole title of the chapter into one line. 


`##` - means here begins subdivision within a highest-order unit. E.g. subchapter within chapter, or a chapter within a book. 

`###` - means here begins a new sub-sub-division ...

`$` - means here ends the text proper (if there is some back-matter that should be left outside the body of text and be sent to the `<back>` element). For example : 

End of the text in [Rulaman](ecocorMD/EzProse_Example_David_Friedrich_Weinland_-_Rulaman_(1878).txt): 

```

Drüben aber auf dem Nufaberg wächst ein uralter Efeu an den Burgruinen. Der
Efeu malt in großen Zügen auf dem grauen Gestein seltsam verschlungene Zeichen.
Wer sie zu deuten versteht, der liest: Rulaman, Welda und Kando.

ENDE
$

                                    ━━━━━━━

Anhang

Worterklärungen

```