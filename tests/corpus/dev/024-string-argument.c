#include <stdio.h>

void print_score(int id, int score) {
    printf("student %d scored %d\n", id, score);
}

int main(void) {
    int i;
    for (i = 1; i <= 3; i++) {
        print_score(i, 80 + i);
    }
    print_score("Alice", 90);
    return 0;
}
