#include <stdio.h>

void print_grade(int score) {
    char grade;
    if (score >= 90) {
        grade = 'A';
    } else if (score >= 75) {
        grade = 'B';
    } else if (score >= 50) {
        grade = 'C';
    } else {
        grade = 'F';
    }
    printf("score %d -> grade %c\n", score, grade);
}

int main(void) {
    print_grade(93);
    print_grade(61);
    print_grade(38);
    return 0;
}
