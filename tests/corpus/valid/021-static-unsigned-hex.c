#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>

static int counter = 0;
static const char *greeting = "hello";

static bool is_even(unsigned long n) {
    return (n % 2) == 0;
}

int main(int argc, char *argv[]) {
    unsigned long big = 0xFFul;
    short small = 12;
    char letter = 'a' + 2;
    bool even = is_even(big);
    int *numbers = calloc(4, sizeof(int));
    if (numbers == NULL) {
        return 1;
    }
    numbers[2] = argc + small;
    counter += numbers[2];
    printf("%s %d %c %d\n", greeting, counter, letter, even);
    free(numbers);
    return 0;
}
