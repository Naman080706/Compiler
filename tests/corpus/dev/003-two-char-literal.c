#include <stdio.h>

int main(void) {
    int score = 78;
    char grade = 'AB';
    if (score >= 90) {
        grade = 'A';
    } else if (score >= 75) {
        grade = 'B';
    } else {
        grade = 'C';
    }
    printf("Score %d gives grade %c\n", score, grade);
    return 0;
}
