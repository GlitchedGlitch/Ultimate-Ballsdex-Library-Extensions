# On line 4 you can put multiple specific credit names separated by a ,

.eval
targets = {}

msg = await message.channel.send("Scanning credits...")

counts = {}

balls = await Ball.all()

for b in balls:
    credits = b.credits or ""

    parts = [x.strip() for x in credits.replace(",", " ").split()]

    unique = set(parts)

    if targets:
        for t in targets:
            if t in unique:
                counts[t] = counts.get(t, 0) + 1
    else:
        for name in unique:
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1

if not counts:
    return "There's no matching credits"

sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

lines = []
for i, (name, c) in enumerate(sorted_counts, 1):
    lines.append(f"{i}. {name}: {c}")

return "Credit Leaderboard:\n\n" + "\n".join(lines) 
