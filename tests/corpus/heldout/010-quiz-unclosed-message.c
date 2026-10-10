#include <stdio.h>

int main(void) {
    int answers[3];
    int correct = 0;
    int i;
    answers[0] = 12;
    answers[1] = 21;
    answers[2] = 30;
    for (i = 0; i < 3; i++) {
        if (answers[i] == (i + 3) * (i + 4)) {
            correct++;
        }
    }
    printf("You got %d right\n, correct);
    if (correct == 3) {
        printf("Perfect score\n");
    }
    printf("Quiz finished\n");
    return 0;
}
