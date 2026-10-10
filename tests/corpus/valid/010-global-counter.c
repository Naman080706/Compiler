#include <stdio.h>

int counter = 0;
int offset = -3;
double rate = 1.5;

void bump(int step) {
    counter += step;
    counter %= 100;
}

int main(void) {
    int i;
    for (i = 0; i < 6; i++) {
        bump(37);
        printf("counter = %d\n", counter);
    }
    counter -= offset;
    counter *= 2;
    counter--;
    printf("final counter = %d, rate = %f\n", counter, rate);
    return 0;
}
