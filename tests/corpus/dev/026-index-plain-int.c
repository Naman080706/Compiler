#include <stdio.h>

int main(void) {
    int scores[3];
    int average = 0;
    int total = 0;
    int i;
    scores[0] = 60;
    scores[1] = 75;
    scores[2] = 90;
    for (i = 0; i < 3; i++) {
        total += scores[i];
    }
    average[0] = total / 3;
    printf("average = %d\n", average);
    return 0;
}
