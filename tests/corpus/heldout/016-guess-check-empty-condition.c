#include <stdio.h>

int check(int guess, int target) {
    if (guess < target) {
        return -1;
    }
    if (guess > ) {
        return 1;
    }
    return 0;
}

int main(void) {
    int target = 42;
    printf("guess 30: %d\n", check(30, target));
    printf("guess 50: %d\n", check(50, target));
    printf("guess 42: %d\n", check(42, target));
    return 0;
}
