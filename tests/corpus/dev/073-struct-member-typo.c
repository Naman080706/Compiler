#include <stdio.h>

struct Student {
    int id;
    int marks;
};

int main(void) {
    struct Student s;
    s.id = 7;
    s.mark = 90;
    printf("%d %d\n", s.id, s.marks);
    return 0;
}
