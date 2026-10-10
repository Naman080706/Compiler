#include <stdio.h>

int swaps_needed(int a, int b, int c) {
    int swaps = 0;
    int tmp;
    if (a > b) {
        tmp = a;
        a = b;
        b = tmp;
        swaps++;
    if (b > c) {
        tmp = b;
        b = c;
        c = tmp;
        swaps++;
    }
    if (a > b) {
        swaps++;
    }
    return swaps;
}

int main(void) {
    printf("swaps for 3 1 2: %d\n", swaps_needed(3, 1, 2));
    printf("swaps for 1 2 3: %d\n", swaps_needed(1, 2, 3));
    return 0;
}
