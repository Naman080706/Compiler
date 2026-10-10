#include <stdio.h>

int main(void) {
    int a = 14;
    int b = 20;
    int c = 9;
    int average = (a + b + c) / 3;
    printf("Average of %d, %d and %d is %d\n", a, b, c, average);
    return 0;
}
/* TODO: round the average instead of cutting it off
   and print a message when the three numbers are equal
