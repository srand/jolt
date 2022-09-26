#include <gmock/gmock.h>

class MyTest2 : public ::testing::Test {
public:
protected:
    void SetUp() override {}
    void TearDown() override {}
    int three{3};
    int four{4};
};

TEST_F(MyTest2, test_three) {
    ASSERT_EQ(three, 3);
}

TEST_F(MyTest2, test_four) {
    ASSERT_EQ(four, 4);
}