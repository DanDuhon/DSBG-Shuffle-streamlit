import json

def remove_supersets(combos):
    """
    Given a list of combos (lists of expansions), 
    return only the minimal sets (no supersets).
    """
    # Convert all combos to sets
    combo_sets = [set(c) for c in combos]
    minimal_sets = []

    for i, c in enumerate(combo_sets):
        if not any(c > other for j, other in enumerate(combo_sets) if i != j):
            minimal_sets.append(c)

    # Convert back to sorted lists for JSON consistency
    return [list(s) for s in minimal_sets]

def transform_json(input_file, output_file):
    # Load the JSON
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    new_data = {}

    for encounter_key, encounter in data.items():
        expansion = encounter["expansion"]
        level = encounter["level"]
        name = encounter["name"]

        # New key format
        new_key = f"{expansion}_{level}_{name}"
        new_data[new_key] = {}

        # Process expansionCombos
        for lvl, combos in encounter["expansionCombos"].items():
            cleaned = remove_supersets(combos)
            new_data[new_key][lvl] = cleaned

    # Write out the transformed JSON
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False)


if __name__ == "__main__":
    transform_json("C:\\Users\\lenle\\GitHub\\DSBG-Shuffle\\lib\\dsbg_shuffle_encounters.json", "C:\\Users\\lenle\\GitHub\\DSBG-Shuffle\\lib\\dsbg_shuffle_encounters2.json")
