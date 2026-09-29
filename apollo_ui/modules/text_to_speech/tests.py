from module import Module


def run_tests():
    module = Module({"base_dir": ".", "validation": True})
    result = module.self_test()

    assert "accent" in result.lower()
    assert module._clean_gender("Female") == "female"
    assert module._clean_accent("British") == "en-GB"
    assert module._clean_accent("American") == "en-US"
    assert module._clean_accent("en-au") == "en-AU"
    assert module._clean_emotion("EXCITED") == "excited"

    deep = module._resolved_modulation(
        module._normalise_profile({"depth": 100})
    )
    light = module._resolved_modulation(
        module._normalise_profile({"depth": -100})
    )
    assert deep["resolved_pitch_semitones"] < light["resolved_pitch_semitones"]

    profile = module._normalise_profile(
        {
            "gender": "male",
            "accent": "Irish",
            "emotion": "confident",
        }
    )
    assert profile["accent"] == "en-IE"

    return result


if __name__ == "__main__":
    print(run_tests())
