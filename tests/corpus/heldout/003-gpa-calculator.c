#include <stdio.h>

int main(void) {
    int grades[4];
    int points = 0;
    int i;
    grades[0] = 8;
    grades[1] = 9;
    grades[2] = 6;
    grades[3] = 10;
    for (i = 0; i < 4; i++) {
        points += grades[i] * 3;
        credits += 3;
    }
    printf("credits taken: %d\n", credits);
    printf("grade point average x10: %d\n", points * 10 / credits);
    return 0;
}
