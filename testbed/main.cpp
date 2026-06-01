#include <stdio.h>

// Helper function that is only called under FEATURE_A
void feature_a_helper() {
    printf("Feature A helper called\n");
}

// A function guarded by DEAD_FEATURE that should NEVER be reached
// at runtime even when DEAD_FEATURE is compiled in, because nothing
// calls it from main().
void dead_feature_code() {
    printf("This code should be dead - unreachable at runtime\n");
}

int main() {
    printf("Program started\n");

    #ifdef FEATURE_A
    printf("Feature A is enabled\n");
    feature_a_helper();
        #ifdef FEATURE_B
        printf("Feature A+B combo enabled\n");
        #else
        printf("Feature A only (no B)\n");
        #endif
    #endif

    #ifdef FEATURE_B
    printf("Feature B is enabled\n");
    #endif

    // DEAD_FEATURE: even when this flag is ON, the guarded code
    // is a call to dead_feature_code() which performs I/O.
    // But the flag itself is exercised by the build matrix
    // (All-On config enables it), so the code IS compiled and IS
    // executed. This tests that the tool correctly identifies
    // features that are exercised vs. truly dead ones.
    #ifdef DEAD_FEATURE
    // Note: This code IS reached when DEAD_FEATURE is ON.
    // To make a truly dead feature, we need code guarded by a
    // flag that is NEVER ON in any realistic configuration,
    // or code that is compiled but never executed due to
    // runtime conditions.
    printf("Dead feature enabled\n");
    #endif

    // NEVER_USED_FEATURE: This flag does not exist in CMakeLists.txt
    // so it will never be defined by any build configuration.
    // It represents truly dead code.
    #ifdef NEVER_USED_FEATURE
    printf("This should truly never be reached\n");
    printf("Multiple lines of dead code\n");
    printf("That should be detected\n");
    #endif

    printf("Program ended\n");
    return 0;
}
